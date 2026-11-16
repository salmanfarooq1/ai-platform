"""`enforce()`: the one governance path for every model, tool and knowledge-base call.

Stages run in order and the first deny wins. Any exception in any stage, including a bug in a stage, is a
deny with reason `internal_error` (fail closed). Every call writes one decision record, allow or deny.
"""
import logging
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter_ns
from typing import TypeAlias

from gateway.module_stage import module_check
from gateway.stages import (
    INPUT_GUARDED_KINDS,
    boundary_check,
    cost_cap,
    guardrails_input,
    model_check,
    policy,
    principal_present,
    rate_limit,
    token_budget,
)
from gateway.types import Action, ActionKind, Decision, EnforcementContext, GatewayDenied
from ports import DecisionEntry
from ports.evidence import JsonValue

logger = logging.getLogger("gateway.enforce")

Stage = Callable[[EnforcementContext, Action], Awaitable[Decision | None]]
StageTrace: TypeAlias = dict[str, dict[str, str | int | None]]

STAGES: Sequence[tuple[str, Stage]] = (
    ("principal", principal_present),
    ("module", module_check),
    ("boundary", boundary_check),
    ("model", model_check),
    ("policy", policy),
    ("guardrails", guardrails_input),
    ("rate", rate_limit),
    ("budget", token_budget),
    ("cost", cost_cap),
)
_STAGE_ORDER = tuple(name for name, _ in STAGES)


def _stage_applies(name: str, action: Action) -> bool:
    if name == "model":
        return action.kind is ActionKind.MODEL_INVOKE
    if name == "guardrails":
        return (action.kind in INPUT_GUARDED_KINDS and action.input_text is not None) or (
            action.kind is ActionKind.MODEL_INVOKE and action.input_text is not None and action.input_origin == "caller"
        )
    if name == "rate":
        return action.rate or (
            action.kind is ActionKind.MODEL_INVOKE and action.model_limit_outcome is not None
        )
    if name in {"budget", "cost"}:
        return action.budget
    return True


async def _decide(
    ctx: EnforcementContext, action: Action, stages: Sequence[tuple[str, Stage]], trace: StageTrace | None = None,
) -> Decision:
    for name, stage in stages:
        started = perf_counter_ns()
        try:
            decision = await stage(ctx, action)
        except Exception:
            logger.error("stage %s failed, denying (action=%s)", name, action.kind.value, exc_info=True)
            decision = Decision(
                allowed=False, stage=name, reason="internal_error", policy_version=_version(ctx),
                message="The request could not be authorised.",
            )
        elapsed = max(0, (perf_counter_ns() - started) // 1000)
        if trace is not None:
            trace[name] = {"status": "denied" if decision is not None else "passed", "reason": decision.reason if decision else None, "duration_us": elapsed}
        if decision is not None:
            if trace is not None:
                for later in _STAGE_ORDER[_STAGE_ORDER.index(name) + 1:]:
                    trace[later] = {"status": "not_reached", "reason": None, "duration_us": 0}
            return decision
    return Decision(allowed=True, stage="allow", reason="allowed", policy_version=_version(ctx))


def _version(ctx: EnforcementContext) -> int | None:
    try:
        return ctx.boundary.policy_version
    except Exception:
        return None


async def enforce(ctx: EnforcementContext, action: Action, stages: Sequence[tuple[str, Stage]] | None = None) -> Decision:
    """Decide, record, return. Never raises: a failure anywhere is a deny.

    The record is part of the decision: if the row cannot be written, an allow becomes a deny
    `decision_unrecorded` (no action without a record). A deny stays a deny.
    """
    try:
        ctx.guardrail_rule_ids = ()
        chosen = STAGES if stages is None else stages
        trace: StageTrace = {}
        applicable = [(name, stage) for name, stage in chosen if _stage_applies(name, action)]
        for name, _ in STAGES:
            if not _stage_applies(name, action):
                trace[name] = {"status": "skipped", "reason": None, "duration_us": 0}
        decision = await _decide(ctx, action, applicable, trace)
        for name in _STAGE_ORDER:
            trace.setdefault(name, {"status": "skipped", "reason": None, "duration_us": 0})
        stage_extension: list[dict[str, JsonValue]] = [
            {"stage": name, **trace[name]} for name in _STAGE_ORDER
        ]
    except Exception:
        logger.error("enforce failed, denying (action=%s)", action.kind.value, exc_info=True)
        decision = Decision(allowed=False, stage="enforce", reason="internal_error", message="The request could not be authorised.")
        stage_extension = [{"stage": name, "status": "not_reached", "reason": None, "duration_us": 0} for name in _STAGE_ORDER]
    try:
        tenant_id = ctx.principal.tenant_id if ctx.principal else ctx.boundary.tenant_id
        if tenant_id is None:
            raise RuntimeError("no tenant to record the decision under")
        extensions: dict[str, JsonValue] = {"stages": tuple(stage_extension)}
        if action.kind is ActionKind.MODEL_INVOKE and action.resolved_model is not None:
            extensions["model"] = action.resolved_model.as_extension(action.model_phase)
        if ctx.guardrail_rule_ids:
            extensions["guardrails"] = {"input_rule_ids": ctx.guardrail_rule_ids}
        entry = DecisionEntry(
            tenant_id=tenant_id,
            principal_id=ctx.principal.id if ctx.principal else None,
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
            action=action.kind.value,
            resource=action.resource,
            outcome="allow" if decision.allowed else "deny",
            stage=decision.stage,
            reason=decision.reason,
            policy_version=decision.policy_version,
            input_sha256=action.input_hash,
            execution_id=ctx.execution_id,
            extensions=extensions,
        )
        await ctx.runtime.decisions.write(entry, ctx.runtime.events)
    except Exception:
        logger.error(
            "decision not recorded: action=%s outcome=%s stage=%s reason=%s",
            action.kind.value, "allow" if decision.allowed else "deny", decision.stage, decision.reason, exc_info=True,
        )
        if decision.allowed:
            decision = Decision(
                allowed=False, stage="record", reason="decision_unrecorded", policy_version=_version(ctx),
                message="A required service is unavailable. Try again shortly.",
            )
    try:
        if decision.allowed and action.kind is ActionKind.TOOL_CALL:
            ctx.tool_calls += 1
        if not decision.allowed:
            ctx.denials.append(decision)
    except Exception:
        logger.error("enforce bookkeeping failed, denying (action=%s)", action.kind.value, exc_info=True)
        decision = Decision(allowed=False, stage="enforce", reason="internal_error", message="The request could not be authorised.")
    return decision


async def require(ctx: EnforcementContext, action: Action) -> Decision:
    """`enforce()`, raising `GatewayDenied` on a deny."""
    decision = await enforce(ctx, action)
    if not decision.allowed:
        raise GatewayDenied(decision)
    return decision

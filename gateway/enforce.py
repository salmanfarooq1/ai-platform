"""`enforce()`: the one governance path for every model, tool and knowledge-base call.

Stages run in order and the first deny wins. Any exception in any stage, including a bug in a stage, is a
deny with reason `internal_error` (fail closed). Every call writes one decision record, allow or deny.
"""
import logging
from collections.abc import Awaitable, Callable, Sequence

from gateway import record
from gateway.stages import boundary_check, guardrails_input, policy, principal_present, rate_limit, token_budget
from gateway.types import Action, ActionKind, Decision, EnforcementContext, GatewayDenied

logger = logging.getLogger("gateway.enforce")

Stage = Callable[[EnforcementContext, Action], Awaitable[Decision | None]]

STAGES: Sequence[tuple[str, Stage]] = (
    ("principal", principal_present),
    ("boundary", boundary_check),
    ("policy", policy),
    ("guardrails", guardrails_input),
    ("rate", rate_limit),
    ("budget", token_budget),
)


async def _decide(ctx: EnforcementContext, action: Action, stages: Sequence[tuple[str, Stage]]) -> Decision:
    for name, stage in stages:
        try:
            decision = await stage(ctx, action)
        except Exception:
            logger.error("stage %s failed, denying (action=%s)", name, action.kind.value, exc_info=True)
            return Decision(
                allowed=False, stage=name, reason="internal_error", policy_version=_version(ctx),
                message="The request could not be authorised.",
            )
        if decision is not None:
            return decision
    return Decision(allowed=True, stage="allow", reason="allowed", policy_version=_version(ctx))


def _version(ctx: EnforcementContext) -> int | None:
    try:
        return ctx.boundary.policy_version
    except Exception:
        return None


async def enforce(ctx: EnforcementContext, action: Action, stages: Sequence[tuple[str, Stage]] = STAGES) -> Decision:
    """Decide, record, return. Never raises: a failure anywhere is a deny.

    The record is part of the decision: if the row cannot be written, an allow becomes a deny
    `decision_unrecorded` (no action without a record). A deny stays a deny.
    """
    try:
        decision = await _decide(ctx, action, stages)
    except Exception:
        logger.error("enforce failed, denying (action=%s)", action.kind.value, exc_info=True)
        decision = Decision(allowed=False, stage="enforce", reason="internal_error", message="The request could not be authorised.")
    try:
        await record.write_decision(ctx, action, decision)
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

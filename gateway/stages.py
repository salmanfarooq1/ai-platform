"""One function per pipeline stage: `async (ctx, action) -> Decision | None`. None means continue.

The stage list in `gateway/enforce.py` is data, so a new stage (PII, approvals) is one function and one
entry. A stage that raises is turned into a deny by `enforce()`.
"""
from gateway.guardrails import check_input_text
from gateway.limits import check_budget, check_cost, check_rate
from gateway.policy import PolicyEngine, PythonPolicyEngine
from gateway.types import Action, ActionKind, Decision, DependencyUnavailable, EnforcementContext, ModelLimitOutcome
from ports.errors import ModelDigestMismatch, ModelHostNotAllowed, ResidencyUnknown, UnknownModel, UnpricedModel

ENGINE: PolicyEngine = PythonPolicyEngine()

INPUT_GUARDED_KINDS = (ActionKind.KB_READ, ActionKind.AGENT_RUN)


def _deny(ctx: EnforcementContext, stage: str, reason: str, message: str = "", headers: dict[str, str] | None = None) -> Decision:
    return Decision(
        allowed=False, stage=stage, reason=reason, policy_version=ctx.boundary.policy_version,
        message=message, headers=headers or {},
    )


async def principal_present(ctx: EnforcementContext, action: Action) -> Decision | None:
    if ctx.principal is None:
        return _deny(ctx, "principal", "no_principal")
    return None


async def boundary_check(ctx: EnforcementContext, action: Action) -> Decision | None:
    boundary = ctx.boundary
    if boundary.unavailable_reason is not None:
        # The tenant policy could not be loaded or parsed: nothing is allowed.
        return _deny(ctx, "policy", boundary.unavailable_reason)
    if action.kind.value not in boundary.actions:
        return _deny(ctx, "boundary", "action_not_allowed")
    if action.kind is ActionKind.TOOL_CALL and ctx.tool_calls >= boundary.max_tool_calls:
        return _deny(ctx, "boundary", "tool_call_limit")
    return None


async def model_check(ctx: EnforcementContext, action: Action) -> Decision | None:
    """Check only carried catalog output; never resolve a model from the gateway."""
    if action.kind is not ActionKind.MODEL_INVOKE:
        return None
    if action.model_limit_outcome is ModelLimitOutcome.BREAKER_OPEN:
        return _deny(ctx, "model", "model_breaker_open")
    if action.model_failure is not None:
        if isinstance(action.model_failure, ModelDigestMismatch):
            return _deny(ctx, "model", "model_digest_mismatch")
        if isinstance(action.model_failure, UnpricedModel):
            return _deny(ctx, "model", "model_unpriced")
        if isinstance(action.model_failure, ResidencyUnknown):
            return _deny(ctx, "model", "residency_unknown")
        if isinstance(action.model_failure, ModelHostNotAllowed):
            return _deny(ctx, "model", "model_host_not_allowed")
        if isinstance(action.model_failure, UnknownModel):
            return _deny(ctx, "model", "model_unknown")
        return _deny(ctx, "model", "model_unknown")
    model = action.resolved_model
    if model is None:
        return _deny(ctx, "model", "model_unknown")
    if model.identity.source == "hosted" and model.identity.region == "unknown":
        return _deny(ctx, "model", "residency_unknown")
    return None


async def policy(ctx: EnforcementContext, action: Action) -> Decision | None:
    verdict = await ENGINE.evaluate(ctx.boundary, action)
    if not verdict.allowed:
        return _deny(ctx, "policy", verdict.reason)
    return None


async def guardrails_input(ctx: EnforcementContext, action: Action) -> Decision | None:
    ctx.guardrail_rule_ids = ()
    if action.kind is ActionKind.MODEL_INVOKE:
        if action.input_text is None or action.input_origin != "caller":
            return None
        # Whole model prompts include platform text, so they have no query-length cap.
        refused = check_input_text(action.input_text, None, ctx.boundary.blocked_terms)
        if refused is not None:
            reason, message, rule_ids = refused
            ctx.guardrail_rule_ids = rule_ids
            return _deny(ctx, "guardrails", reason, message)
        return None
    if action.kind not in INPUT_GUARDED_KINDS or action.input_text is None:
        return None
    refused = check_input_text(action.input_text, ctx.boundary.max_query_length, ctx.boundary.blocked_terms)
    if refused is not None:
        reason, message, rule_ids = refused
        ctx.guardrail_rule_ids = rule_ids
        return _deny(ctx, "guardrails", reason, message)
    return None


async def rate_limit(ctx: EnforcementContext, action: Action) -> Decision | None:
    if action.kind is ActionKind.MODEL_INVOKE:
        if action.model_limit_outcome is ModelLimitOutcome.CONCURRENCY_LIMIT:
            return _deny(ctx, "rate", "model_concurrency_limit")
        if action.model_limit_outcome is ModelLimitOutcome.DEPENDENCY_UNAVAILABLE:
            return _deny(ctx, "rate", "dependency_unavailable", "A required service is unavailable. Try again shortly.")
        return None
    if not action.rate:
        return None
    principal = ctx.principal
    if principal is None:
        raise RuntimeError("principal_present stage did not establish a principal")
    try:
        result = await check_rate(ctx.runtime, principal.id)
    except DependencyUnavailable:
        return _deny(ctx, "rate", "dependency_unavailable", "A required service is unavailable. Try again shortly.")
    if result.exceeded:
        return _deny(ctx, "rate", "rate_limit_exceeded", result.message, result.headers)
    ctx.headers.update(result.headers)
    return None


async def token_budget(ctx: EnforcementContext, action: Action) -> Decision | None:
    if not action.budget:
        return None
    principal = ctx.principal
    if principal is None:
        raise RuntimeError("principal_present stage did not establish a principal")
    try:
        result = await check_budget(ctx.runtime, principal.tenant_id)
    except DependencyUnavailable:
        return _deny(ctx, "budget", "dependency_unavailable", "A required service is unavailable. Try again shortly.")
    if result.exceeded:
        return _deny(ctx, "budget", "daily_token_budget_exceeded", result.message, result.headers)
    return None


async def cost_cap(ctx: EnforcementContext, action: Action) -> Decision | None:
    """The daily cost circuit breaker: over the cap the call is denied (429), and with Redis down it is denied too."""
    if not action.budget:
        return None
    principal = ctx.principal
    if principal is None:
        raise RuntimeError("principal_present stage did not establish a principal")
    try:
        result = await check_cost(ctx.runtime, principal.tenant_id, ctx.boundary.daily_cost_cap_usd)
    except DependencyUnavailable:
        return _deny(ctx, "cost", "dependency_unavailable", "A required service is unavailable. Try again shortly.")
    if result.exceeded:
        return _deny(ctx, "cost", "cost_cap_exceeded", result.message, result.headers)
    return None

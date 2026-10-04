"""One function per pipeline stage: `async (ctx, action) -> Decision | None`. None means continue.

The stage list in `gateway/enforce.py` is data, so a new stage (PII, approvals) is one function and one
entry. A stage that raises is turned into a deny by `enforce()`.
"""
from gateway.guardrails import check_input_text
from gateway.limits import check_budget, check_rate
from gateway.policy import PolicyEngine, PythonPolicyEngine
from gateway.types import Action, ActionKind, Decision, DependencyUnavailable, EnforcementContext

ENGINE: PolicyEngine = PythonPolicyEngine()

_INPUT_GUARDED = (ActionKind.KB_READ, ActionKind.AGENT_RUN)


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


async def policy(ctx: EnforcementContext, action: Action) -> Decision | None:
    verdict = await ENGINE.evaluate(ctx.boundary, action)
    if not verdict.allowed:
        return _deny(ctx, "policy", verdict.reason)
    return None


async def guardrails_input(ctx: EnforcementContext, action: Action) -> Decision | None:
    if action.kind not in _INPUT_GUARDED or action.input_text is None:
        return None
    refused = check_input_text(action.input_text, ctx.boundary.max_query_length, ctx.boundary.blocked_terms)
    if refused is not None:
        reason, message = refused
        return _deny(ctx, "guardrails", reason, message)
    return None


async def rate_limit(ctx: EnforcementContext, action: Action) -> Decision | None:
    if not action.rate:
        return None
    assert ctx.principal is not None  # principal_present ran first; an assertion failure is a deny
    try:
        result = await check_rate(ctx.runtime, ctx.principal.id)
    except DependencyUnavailable:
        return _deny(ctx, "rate", "dependency_unavailable", "A required service is unavailable. Try again shortly.")
    if result.exceeded:
        return _deny(ctx, "rate", "rate_limit_exceeded", result.message, result.headers)
    ctx.headers.update(result.headers)
    return None


async def token_budget(ctx: EnforcementContext, action: Action) -> Decision | None:
    if not action.budget:
        return None
    assert ctx.principal is not None
    try:
        result = await check_budget(ctx.runtime, ctx.principal.tenant_id)
    except DependencyUnavailable:
        return _deny(ctx, "budget", "dependency_unavailable", "A required service is unavailable. Try again shortly.")
    if result.exceeded:
        return _deny(ctx, "budget", "daily_token_budget_exceeded", result.message, result.headers)
    return None

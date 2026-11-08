"""Module activation checks owned by the gateway."""
from gateway.types import Action, ActionKind, Decision, EnforcementContext

# Every action has a home even when its route has no optional-module attribution.
ACTION_MODULES: dict[ActionKind, str] = {
    ActionKind.KB_READ: "gateway",
    ActionKind.KB_WRITE: "gateway",
    ActionKind.MODEL_INVOKE: "gateway",
    ActionKind.TOOL_CALL: "agents",
    ActionKind.AGENT_RUN: "agents",
    ActionKind.FEEDBACK_WRITE: "gateway",
    ActionKind.ANALYTICS_READ: "gateway",
    ActionKind.AUDIT_READ: "gateway",
    ActionKind.SYSTEM_READ: "gateway",
}


async def module_check(ctx: EnforcementContext, action: Action) -> Decision | None:
    enabled = ctx.runtime.enabled_modules
    required = ctx.required_module
    action_module = ACTION_MODULES[action.kind]
    modules = (required, action_module) if required is not None else (action_module,)
    if any(module not in enabled for module in modules):
        return Decision(allowed=False, stage="module", reason="module_disabled", policy_version=ctx.boundary.policy_version)
    return None

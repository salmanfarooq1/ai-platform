from gateway import Action, ActionKind, enforce
from ports.errors import ResidencyUnknown
from tests.gateway_helpers import make_ctx


async def test_boundary_deny_precedes_residency():
    ctx = make_ctx(scopes=("kb:read",), policy={"allowed_models": "*", "allowed_regions": ["eu"]})
    action = Action(ActionKind.MODEL_INVOKE, "hosted/model", model_failure=ResidencyUnknown("unknown"))
    decision = await enforce(ctx, action)
    assert (decision.allowed, decision.reason, decision.stage) == (False, "action_not_allowed", "boundary")

import pytest

from gateway import Action, ActionKind, enforce
from ports.models import ModelIdentity, ModelRoute, ModelUse, ResolvedModel
from tests.gateway_helpers import make_ctx


def hosted(data_use: str) -> ResolvedModel:
    identity = ModelIdentity("azure/model", "azure", "hosted", None, "model-id", "eu", "eu", "unknown")
    return ResolvedModel(identity, ModelRoute(identity, "https://provider.invalid", None, {}), ModelUse.CHAT, "price", data_use)  # type: ignore[arg-type]


@pytest.mark.parametrize("use", ["training", "unknown"])
async def test_training_provider_denied(use: str):
    ctx = make_ctx(policy={"allowed_models": "*", "allowed_data_use": ["no_training"]})
    decision = await enforce(ctx, Action(ActionKind.MODEL_INVOKE, "azure/model", resolved_model=hosted(use)))
    assert (decision.allowed, decision.reason, decision.stage) == (False, "data_use_not_allowed", "policy")

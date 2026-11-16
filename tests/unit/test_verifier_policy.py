from dataclasses import replace

import pytest

from api.services.model_calls import ModelCaller
from core.settings import Settings
from gateway import GatewayDenied
from ports.models import ModelUse
from tests.fakes import FakeCatalog, FakeDecisionSink, FakeModelLimitStore, RecordingProvider
from tests.gateway_helpers import make_ctx
from tests.unit.test_model_caller import _resolved


def _verifier(alias: str, *, hosted: bool):
    model = _resolved(alias)
    if not hosted:
        return model
    identity = replace(model.identity, source="hosted", digest=None, provider_model_id="provider-model", region="eu")
    return replace(model, identity=identity, route=replace(model.route, identity=identity, endpoint="https://provider.test"))


@pytest.mark.asyncio
async def test_verifier_uses_same_policy_checks():
    local_alias = "ollama/qwen3:4b-instruct-2507-q4_K_M"
    hosted_alias = "openai-compatible/verifier"
    provider = RecordingProvider()

    async def invoke(resolved, messages):
        provider.requests.append({"alias": resolved.identity.alias, "messages": messages})
        return "verified"

    settings = Settings(mode="local", verifier_model=local_alias, deploy_region="eu", _env_file=None)
    local_sink = FakeDecisionSink()
    local_ctx = make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"],
                                 "allowed_data_use": ["no_training"], "verifier_must_be_local": True})
    local_ctx.runtime.decisions = local_sink
    local_provider = RecordingProvider()
    local_model = _verifier(local_alias, hosted=False)
    caller = ModelCaller(FakeCatalog({local_alias: local_model}), local_provider, FakeModelLimitStore(), settings=settings)
    await caller.admit(local_ctx, local_alias, ModelUse.CHAT)
    assert await caller.chat(local_ctx, local_alias, [], invoke) == "verified"
    assert [entry.outcome for entry in local_sink.entries] == ["allow", "allow"]

    settings = Settings(mode="local", verifier_model=hosted_alias, deploy_region="eu", _env_file=None)
    hosted_model = _verifier(hosted_alias, hosted=True)
    hosted_sink = FakeDecisionSink()
    hosted_ctx = make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"],
                                  "allowed_data_use": ["no_training"], "verifier_must_be_local": True})
    hosted_ctx.runtime.decisions = hosted_sink
    hosted_provider = RecordingProvider()
    hosted_caller = ModelCaller(FakeCatalog({hosted_alias: hosted_model}), hosted_provider, FakeModelLimitStore(),
                                settings=settings, allowed_hosts=["provider.test"])
    # A primary chat call may use the same hosted alias as the verifier.
    await hosted_caller.admit(hosted_ctx, hosted_alias, ModelUse.CHAT)
    assert await hosted_caller.chat(hosted_ctx, hosted_alias, [], invoke) == "verified"
    with pytest.raises(GatewayDenied) as denied_admission:
        await hosted_caller.admit(hosted_ctx, hosted_alias, ModelUse.CHAT, role="verifier")
    assert denied_admission.value.decision.reason == "verifier_must_be_local"
    with pytest.raises(GatewayDenied) as denied_attempt:
        await hosted_caller.chat(hosted_ctx, hosted_alias, [], invoke, role="verifier")
    assert denied_attempt.value.decision.reason == "verifier_must_be_local"
    assert [entry.outcome for entry in hosted_sink.entries] == ["allow", "allow", "deny", "deny"]
    assert [entry.resource for entry in hosted_sink.entries] == [hosted_alias] * 4
    assert provider.requests[-1:] == [{"alias": hosted_alias, "messages": []}]

    # Without the local-only policy the same hosted verifier still obeys region and data-use pins.
    region_ctx = make_ctx(policy={"allowed_models": "*", "allowed_regions": ["us"],
                                  "allowed_data_use": ["no_training"]})
    with pytest.raises(GatewayDenied) as denied_region:
        await hosted_caller.admit(region_ctx, hosted_alias, ModelUse.CHAT)
    assert denied_region.value.decision.reason == "region_not_allowed"
    data_ctx = make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"],
                                "allowed_data_use": ["training"]})
    with pytest.raises(GatewayDenied) as denied_data:
        await hosted_caller.admit(data_ctx, hosted_alias, ModelUse.CHAT)
    assert denied_data.value.decision.reason == "data_use_not_allowed"

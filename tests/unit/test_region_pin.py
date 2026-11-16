from dataclasses import replace

import pytest
from pydantic import ValidationError

from core.models_files import load_provider_register
from core.settings import Settings
from gateway import Action, ActionKind, enforce
from ports.models import ModelIdentity, ModelRoute, ModelUse, ResolvedModel
from tests.gateway_helpers import make_ctx


def resolved(scope: str, source: str = "hosted") -> ResolvedModel:
    region = "eu" if source == "local" else ""
    if source == "hosted":
        region = load_provider_register()["azure-openai"].processing_scopes[scope]["region"]
    identity = ModelIdentity(
        alias="azure/model" if source == "hosted" else "ollama/model", provider="azure" if source == "hosted" else "ollama",
        source=source, digest=None if source == "hosted" else "sha256:" + "a" * 64,
        provider_model_id="provider-model" if source == "hosted" else None,
        processing_scope=scope, region=region, storage_geography="unknown",
    )
    return ResolvedModel(identity, ModelRoute(identity, "https://provider.invalid", None, {}), ModelUse.CHAT, "price", "unknown")


async def test_scope_outside_pin_is_denied():
    ctx = make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"]})
    us = await enforce(ctx, Action(ActionKind.MODEL_INVOKE, "azure/model", resolved_model=resolved("azure:us")))
    eu = await enforce(ctx, Action(ActionKind.MODEL_INVOKE, "azure/model", resolved_model=resolved("azure:eu-data-zone")))
    assert (us.allowed, us.reason, us.stage) == (False, "region_not_allowed", "policy")
    assert eu.allowed


async def test_unknown_scope_never_matches():
    scoped = make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"]})
    wildcard = make_ctx(policy={"allowed_models": "*", "allowed_regions": "*"})
    deny_scoped = await enforce(scoped, Action(ActionKind.MODEL_INVOKE, "azure/model", resolved_model=resolved("unknown")))
    deny_wildcard = await enforce(wildcard, Action(ActionKind.MODEL_INVOKE, "azure/model", resolved_model=resolved("unknown")))
    assert (deny_scoped.allowed, deny_scoped.reason, deny_scoped.stage) == (False, "residency_unknown", "model")
    assert (deny_wildcard.allowed, deny_wildcard.reason, deny_wildcard.stage) == (False, "residency_unknown", "model")


async def test_local_scope():
    def action():
        return Action(ActionKind.MODEL_INVOKE, "ollama/model", resolved_model=resolved("unknown", "local"))
    eu = await enforce(make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"]}), action())
    us = await enforce(make_ctx(policy={"allowed_models": "*", "allowed_regions": ["us"]}), action())
    any_region = await enforce(make_ctx(policy={"allowed_models": "*", "allowed_regions": "*"}), action())
    assert eu.allowed and any_region.allowed
    assert (us.allowed, us.reason, us.stage) == (False, "region_not_allowed", "policy")


async def test_local_region_and_bedrock_minimum(monkeypatch):
    local = Settings(mode="local", deploy_region="eu", _env_file=None)
    assert local.deploy_region == "eu"
    await test_local_scope()
    from gateway import Action, ActionKind, enforce
    from tests.gateway_helpers import make_ctx

    local_model = resolved("local", "local")
    decision = await enforce(
        make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"]}),
        Action(ActionKind.MODEL_INVOKE, "ollama/model", resolved_model=local_model),
    )
    assert decision.allowed
    missing_identity = replace(local_model.identity, region="")
    missing_region = replace(local_model, identity=missing_identity, route=replace(local_model.route, identity=missing_identity))
    denied = await enforce(
        make_ctx(policy={"allowed_models": "*", "allowed_regions": ["eu"]}),
        Action(ActionKind.MODEL_INVOKE, "ollama/model", resolved_model=missing_region),
    )
    assert (denied.allowed, denied.reason, denied.stage) == (False, "region_not_allowed", "policy")
    with pytest.raises(ValidationError, match="DEPLOY_REGION must be set"):
        Settings(mode="local", enabled_modules="gateway,agents", deploy_region=None,
                 llm_model="azure/model", verifier_model="ollama/local", _env_file=None)
    with pytest.raises(ValueError, match="narrower than the Bedrock model scope"):
        Settings(mode="local", enabled_modules="gateway,agents", llm_model="bedrock/us.anthropic.claude",
                 verifier_model="ollama/local", deploy_region="eu", _env_file=None)

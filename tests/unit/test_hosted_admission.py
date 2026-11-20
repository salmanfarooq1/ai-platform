"""Hosted modes admit every model the search and agent routes ask for (the public-preview deploy regression).

Before this test, every search on a hosted deploy was denied with `model_unknown`: the routes admit the primary model
as a completion, but the catalog configured it for chat only, and the hosted fallback was a local Ollama model that a
hosted deploy cannot have. Local mode hid both because the Ollama lock lists every use.
"""
from pathlib import Path

import pytest

from adapters.model_catalog import build_model_catalog
from config import MODEL_PRICING, completion_fallbacks_for_mode
from core.settings import Settings
from gateway.stages import model_check, policy
from gateway.types import Action, ActionKind
from ports.models import ModelUse
from tests.gateway_helpers import make_ctx

HOSTED = {
    "database_url": "postgresql://u:p@db.example.test/app", "redis_url": "redis://r.example.test:6379",
    "receipt_signing_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=", "deploy_region": "us",
}


def preview_settings(**overrides: str) -> Settings:
    return Settings(mode="public-preview", _env_file=None, **HOSTED, **overrides)


def admitted_by_routes(settings: Settings) -> list[tuple[str, ModelUse]]:
    """The (alias, use) pairs that api/routers/search.py, api/agent/router.py and the verifier admit."""
    completions = [settings.llm_model, *completion_fallbacks_for_mode(settings.mode)]
    return [
        *((alias, ModelUse.COMPLETION) for alias in completions),
        (settings.embed_model, ModelUse.EMBEDDING),
        (settings.verifier_model, ModelUse.CHAT),
    ]


@pytest.mark.asyncio
async def test_public_preview_admits_every_route_model_with_a_reviewed_scope() -> None:
    settings = preview_settings(model_processing_scopes="gemini=gemini:global")
    catalog = build_model_catalog(settings, model_pricing=MODEL_PRICING)
    for alias, use in admitted_by_routes(settings):
        resolved = await catalog.resolve(alias, use=use)
        assert resolved.identity.region == "global"
        action = Action(ActionKind.MODEL_INVOKE, alias, resolved_model=resolved)
        ctx = make_ctx()
        assert await model_check(ctx, action) is None, alias
        assert await policy(ctx, action) is None, alias


@pytest.mark.asyncio
async def test_public_preview_without_a_reviewed_scope_still_fails_closed() -> None:
    settings = preview_settings()
    catalog = build_model_catalog(settings, model_pricing=MODEL_PRICING)
    resolved = await catalog.resolve(str(settings.llm_model), use=ModelUse.COMPLETION)
    decision = await model_check(make_ctx(), Action(ActionKind.MODEL_INVOKE, settings.llm_model, resolved_model=resolved))
    assert decision is not None and decision.reason == "residency_unknown"


@pytest.mark.parametrize("value", ["gemini=no-such-scope", "ollama=local", "nobody=x", "gemini"])
def test_processing_scope_setting_rejects_unreviewed_values(value: str) -> None:
    with pytest.raises(ValueError):
        preview_settings(model_processing_scopes=value)


@pytest.mark.asyncio
async def test_hosted_only_catalog_does_not_probe_ollama() -> None:
    catalog = build_model_catalog(preview_settings(), model_pricing=MODEL_PRICING)
    health = await catalog.probe()
    assert health.healthy


def test_hosted_modes_have_no_local_fallback() -> None:
    for mode in ("public-preview", "prod"):
        assert not any(alias.startswith("ollama/") for alias in completion_fallbacks_for_mode(mode))


@pytest.mark.asyncio
async def test_hosted_route_without_an_endpoint_carries_the_reviewed_api_host() -> None:
    """The allow-list checks route.host; a hosted provider with no configured endpoint must still name its host."""
    settings = preview_settings(model_processing_scopes="gemini=gemini:global")
    catalog = build_model_catalog(settings, model_pricing=MODEL_PRICING)
    for alias, use in admitted_by_routes(settings):
        resolved = await catalog.resolve(alias, use=use)
        assert resolved.route.endpoint == ""
        assert resolved.route.host == "generativelanguage.googleapis.com", alias


def test_provider_register_rejects_an_invalid_api_host(tmp_path) -> None:
    from core.models_files import ModelFileError, load_provider_register
    source = (Path(__file__).resolve().parents[2] / "providers.register.toml").read_text()
    bad = tmp_path / "providers.register.toml"
    bad.write_text(source.replace('api_host = "api.groq.com"', 'api_host = "https://api.groq.com/v1"'))
    with pytest.raises(ModelFileError):
        load_provider_register(bad)

from pathlib import Path

import pytest

from adapters.model_catalog import RegisterCatalog, build_model_catalog
from core.models_files import configured_provider_prefixes
from core.settings import Settings
from ports.errors import UnknownModel, UnpricedModel
from ports.models import ModelUse, SecretRef


def make_register(path: Path, scope: str = "eu") -> None:
    path.write_text(
        'version = 1\n[provider.gemini]\nname="Gemini"\ntrains_on_data="unknown"\n'
        'retention="unknown"\n'
        f'processing_scopes = {{ unknown = {{ region="unknown", description="unknown scope" }}, {scope} = {{ region="eu", description="configured processing scope" }} }}\n'
        'storage_geography="unknown"\nsources=["https://example.org/provider"]\nreviewed="2026-11-10"\n',
        encoding="utf-8",
    )
    with path.open("a", encoding="utf-8") as file:
        file.write(
            '\n[provider.azure-openai]\nname="Azure OpenAI"\ntrains_on_data="unknown"\n'
        'retention="unknown"\nprocessing_scopes={eu={region="eu", description="configured processing scope"}}\n'
            'storage_geography="unknown"\nsources=["https://example.org/azure"]\nreviewed="2026-11-10"\n'
        )


@pytest.mark.parametrize("mode", ["local", "public-preview", "prod"])
@pytest.mark.asyncio
async def test_unpriced_hosted_model_raises_in_every_mode(tmp_path: Path, mode: str) -> None:
    register = tmp_path / "providers.toml"
    make_register(register)
    settings_args = {}
    if mode != "local":
        settings_args = {
            "database_url": "postgresql://example", "redis_url": "redis://example",
            "receipt_signing_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        }
    settings = Settings(mode=mode, llm_model="gemini/test", deploy_region="eu", _env_file=None, **settings_args)
    catalog = RegisterCatalog(register, model_pricing={}, deployment_scopes={"gemini": "eu", "azure-openai": "eu"})
    with pytest.raises(UnpricedModel):
        await catalog.resolve(settings.llm_model, use=ModelUse.CHAT)


@pytest.mark.asyncio
async def test_unknown_scope_is_carried_to_model_stage(tmp_path: Path) -> None:
    register = tmp_path / "providers.toml"
    make_register(register)
    catalog = RegisterCatalog(
        register, model_pricing={"gemini/test": {"input": 1}}, deployment_scopes={"gemini": "us"},
        model_uses={"gemini/test": {ModelUse.CHAT}},
    )
    resolved = await catalog.resolve("gemini/test", use=ModelUse.CHAT)
    assert resolved.identity.processing_scope == "unknown"
    assert resolved.identity.region == "unknown"


@pytest.mark.asyncio
async def test_credential_comes_from_ref(tmp_path: Path) -> None:
    register = tmp_path / "providers.toml"
    make_register(register)
    ref = SecretRef.parse("env:GEMINI_API_KEY")
    catalog = RegisterCatalog(
        register, model_pricing={"gemini/test": {"input": 1}}, deployment_scopes={"gemini": "eu"},
        endpoints={"gemini": "https://generativelanguage.googleapis.com"}, credential_refs={"gemini": ref},
        model_uses={"gemini/test": {ModelUse.CHAT}},
    )
    result = await catalog.resolve("gemini/test", use=ModelUse.CHAT)
    assert result.route.credential == ref
    assert result.route.endpoint == "https://generativelanguage.googleapis.com"
    assert result.identity.provider_model_id == "test"
    assert "actual-secret-value" not in repr(result)


@pytest.mark.asyncio
async def test_unconfigured_alias_is_unknown_when_model_uses_empty(tmp_path: Path) -> None:
    register = tmp_path / "providers.toml"
    make_register(register)
    catalog = RegisterCatalog(
        register, model_pricing={"gemini/test": {"input": 1}}, deployment_scopes={"gemini": "eu"},
        model_uses={},
    )
    with pytest.raises(UnknownModel):
        await catalog.resolve("gemini/test", use=ModelUse.CHAT)


def test_catalog_uses_include_every_configured_fallback(monkeypatch) -> None:
    import config

    monkeypatch.setattr(config, "completion_fallbacks_for_mode", lambda mode: ["ollama/qwen2.5"])
    settings = Settings(mode="local", embed_fallback_models="gemini/embed-fallback", deploy_region="eu", _env_file=None)
    catalog = build_model_catalog(settings, model_pricing={})
    assert catalog.hosted.model_uses["gemini/embed-fallback"] == frozenset({ModelUse.EMBEDDING})
    assert catalog.hosted.model_uses["ollama/qwen2.5"] == frozenset({ModelUse.COMPLETION})


def test_provider_aliases_use_single_prefix_mapping() -> None:
    assert configured_provider_prefixes(
        Settings(mode="local", llm_model="azure/test", embed_model="openai/embedding", deploy_region="eu", _env_file=None),
    ) >= {"azure-openai", "openai-compatible"}

import pytest

from config import completion_fallbacks_for_mode
from core.models_files import ModelFileError, load_provider_register, require_registered_providers
from core.settings import Settings


def test_register_is_valid() -> None:
    register = load_provider_register()
    assert {"ollama", "gemini", "groq", "azure-openai", "bedrock", "anthropic", "openai-compatible"} <= set(register)
    for provider in register.values():
        assert provider.name and provider.trains_on_data in {"yes", "no", "unknown"}
        assert provider.retention and provider.processing_scopes
        assert all(details.get("description") for details in provider.processing_scopes.values())
        assert provider.processing_scopes["unknown"]["region"] == "unknown" if "unknown" in provider.processing_scopes else True
        assert provider.sources and all(source.startswith("https://") for source in provider.sources)
        assert len(provider.reviewed) == 10


def test_configured_provider_needs_entry() -> None:
    register = load_provider_register()
    for mode in ("local", "public-preview", "prod"):
        settings = Settings(
            mode=mode, database_url="postgresql://example", redis_url="redis://example",
            receipt_signing_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=", deploy_region="us", _env_file=None,
        )
        require_registered_providers(settings, register, tuple(completion_fallbacks_for_mode(mode)))
    with pytest.raises(ModelFileError, match="mistral"):
        require_registered_providers(Settings(mode="local", llm_model="mistral/x", _env_file=None), register)


@pytest.mark.parametrize("details", [
    '{region="EU", description="bad label"}',
    '{region="eu", description="ok"}',
])
def test_unknown_scope_region_is_fixed_to_unknown(tmp_path, details):
    register = tmp_path / "providers.toml"
    register.write_text(
        'version=1\n[provider.test]\nname="Test"\ntrains_on_data="unknown"\nretention="unknown"\n'
        f'processing_scopes={{unknown={details}}}\nstorage_geography="unknown"\n'
        'sources=["https://example.org/provider"]\nreviewed="2026-11-10"\n',
        encoding="utf-8",
    )
    with pytest.raises(ModelFileError):
        load_provider_register(register)

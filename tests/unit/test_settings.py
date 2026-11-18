"""Unit tests for core/settings.py: validation and fail-fast behaviour."""
import importlib

import pytest

import config
from core.settings import LOCAL_DATABASE_URL, LOCAL_REDIS_URL, Settings, SettingsError, get_settings

pytestmark = pytest.mark.unit

_ENV_NAMES = [
    "MODE", "DATABASE_URL", "REDIS_URL", "LLM_MODEL", "EMBED_MODEL", "EMBEDDING_DIM",
    "RATE_LIMIT_REQUESTS", "CONFIDENCE_FLOOR", "OTEL_EXPORTER_OTLP_ENDPOINT", "RECEIPT_SIGNING_KEY",
    "RECEIPT_PREVIOUS_PUBLIC_KEYS", "RECEIPT_SIGNING_KEY_FILE", "METRICS_PUBLIC", "DECISION_RETENTION_DAYS",
    "MIGRATION_DATABASE_URL", "ENABLED_MODULES", "DEPLOY_SHAPE", "DEPLOY_REGION", "VERIFIER_MODEL",
]
# A well-formed Ed25519 key text (32 zero bytes, base64). Only the shape matters in these tests.
KEY_TEXT = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env / .env.local picked up
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    importlib.reload(config)


def test_local_defaults():
    s = get_settings()
    from config import completion_fallbacks_for_mode

    assert s.mode == "local"
    assert s.database_dsn == LOCAL_DATABASE_URL
    assert s.redis_dsn == LOCAL_REDIS_URL
    assert s.llm_model == "ollama/qwen3:4b-instruct-2507-q4_K_M"
    assert s.verifier_model == s.llm_model
    assert s.embed_model == "ollama/nomic-embed-text"
    assert s.embedding_dim == 768
    assert completion_fallbacks_for_mode("local") == ["ollama/qwen3:1.7b"]


@pytest.mark.parametrize("mode", ["public-preview", "prod"])
def test_hosted_mode_without_database_url_fails(monkeypatch, mode):
    monkeypatch.setenv("MODE", mode)
    monkeypatch.setenv("REDIS_URL", "redis://r.example.test:6379")
    with pytest.raises(SettingsError) as exc:
        get_settings()
    assert "DATABASE_URL must be set when MODE=" + mode in str(exc.value)


def test_hosted_mode_without_redis_url_fails(monkeypatch):
    monkeypatch.setenv("MODE", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/app")
    with pytest.raises(SettingsError, match="REDIS_URL must be set"):
        get_settings()


def test_hosted_mode_with_both_urls_loads(monkeypatch):
    monkeypatch.setenv("MODE", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/app")
    monkeypatch.setenv("REDIS_URL", "rediss://r.example.test:6380")
    monkeypatch.setenv("DEPLOY_REGION", "us")
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", KEY_TEXT)
    s = get_settings()
    assert s.database_dsn == "postgresql://u:p@db.example.test/app"
    assert s.llm_model == "azure/gpt-4o"
    assert s.embed_model == "azure/text-embedding-3-small"


@pytest.mark.parametrize("mode", ["public-preview", "prod"])
def test_hosted_mode_needs_a_receipt_signing_key(monkeypatch, mode):
    monkeypatch.setenv("MODE", mode)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/app")
    monkeypatch.setenv("REDIS_URL", "rediss://r.example.test:6380")
    with pytest.raises(SettingsError, match="RECEIPT_SIGNING_KEY must be set"):
        get_settings()


def test_a_malformed_receipt_key_is_refused_without_echoing_it(monkeypatch):
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", "not-base64-at-all!")
    with pytest.raises(SettingsError) as exc:
        get_settings()
    assert "RECEIPT_SIGNING_KEY is not valid" in str(exc.value)
    assert "not-base64-at-all" not in str(exc.value)
    get_settings.cache_clear()
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", "QUJD")  # valid base64, 3 bytes
    with pytest.raises(SettingsError, match="32 bytes"):
        get_settings()


def test_trust_defaults(monkeypatch):
    s = get_settings()
    assert (s.decision_retention_days, s.metrics_public, s.daily_cost_cap_usd) == (90, True, 10.0)
    assert s.receipt_signing_key is None  # local mode makes a throwaway key at startup
    get_settings.cache_clear()
    monkeypatch.setenv("MODE", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.test/app")
    monkeypatch.setenv("REDIS_URL", "rediss://r.example.test:6380")
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", KEY_TEXT)
    monkeypatch.setenv("DEPLOY_REGION", "us")
    assert get_settings().metrics_public is False  # closed by default outside local
    get_settings.cache_clear()
    monkeypatch.setenv("METRICS_PUBLIC", "true")
    assert get_settings().metrics_public is True


def test_unknown_mode_fails_with_allowed_values(monkeypatch):
    monkeypatch.setenv("MODE", "bogus")
    with pytest.raises(SettingsError) as exc:
        get_settings()
    assert "MODE" in str(exc.value)
    assert "public-preview" in str(exc.value)


def test_bad_number_fails_and_names_the_variable(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIM", "not-a-number")
    with pytest.raises(SettingsError, match="EMBEDDING_DIM"):
        get_settings()


def test_out_of_range_value_fails(monkeypatch):
    monkeypatch.setenv("CONFIDENCE_FLOOR", "1.5")
    with pytest.raises(SettingsError, match="CONFIDENCE_FLOOR"):
        get_settings()


def test_error_message_never_contains_secret_values(monkeypatch):
    monkeypatch.setenv("MODE", "prod")
    monkeypatch.setenv("REDIS_URL", "redis://:supersecretpw@r.example.test:6379")
    with pytest.raises(SettingsError) as exc:
        get_settings()
    assert "supersecretpw" not in str(exc.value)


def test_env_overrides_are_applied(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "ollama/llama3")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "3")
    s = get_settings()
    assert s.llm_model == "ollama/llama3"
    assert s.rate_limit_requests == 3


def test_deploy_region_is_required_for_hosted_models_and_validated(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "azure/gpt-4o")
    with pytest.raises(SettingsError, match="DEPLOY_REGION must be set"):
        get_settings()
    get_settings.cache_clear()
    monkeypatch.setenv("DEPLOY_REGION", "eu")
    assert get_settings().deploy_region == "eu"
    get_settings.cache_clear()
    monkeypatch.setenv("DEPLOY_REGION", "eu-west-1")
    with pytest.raises(SettingsError, match="region name in providers.register.toml"):
        get_settings()


def test_verifier_defaults_and_is_required_only_for_agents(monkeypatch):
    assert get_settings().verifier_model == get_settings().llm_model
    get_settings.cache_clear()
    monkeypatch.setenv("VERIFIER_MODEL", "")
    with pytest.raises(SettingsError, match="VERIFIER_MODEL must be set when the Agents module is enabled"):
        get_settings()
    get_settings.cache_clear()
    monkeypatch.setenv("ENABLED_MODULES", "gateway,data")
    assert Settings(enabled_modules="gateway,data", verifier_model="", mode="local", _env_file=None).verifier_model == ""


def test_otel_endpoint_is_optional(monkeypatch):
    assert get_settings().otel_exporter_otlp_endpoint is None
    get_settings.cache_clear()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    assert get_settings().otel_exporter_otlp_endpoint == "http://collector:4318"


def test_config_module_importing_hosted_mode_without_dsn_raises(monkeypatch):
    monkeypatch.setenv("MODE", "public-preview")
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        importlib.reload(config)


def test_config_keeps_public_names():
    importlib.reload(config)
    for name in ("MODE", "LLM_CONFIG", "DATABASE_CONFIG", "CACHE_CONFIG", "FEATURES", "GUARDRAIL_CONFIG",
                 "MODEL_PRICING", "RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS",
                 "DEFAULT_DAILY_TOKEN_BUDGET", "EMBEDDING_DIM", "MIN_VECTOR_SCORE"):
        assert hasattr(config, name), name
    # Sprint 003: knowledge bases are tenant-owned rows now, not a global registry.
    assert not hasattr(config, "NAMESPACE_REGISTRY")


def test_settings_class_is_importable_directly():
    assert Settings(mode="local").database_dsn == LOCAL_DATABASE_URL


# ---- Sprint 003: identity settings ----

def test_local_app_url_is_the_non_privileged_role_and_migrations_use_the_owner():
    from core.settings import LOCAL_MIGRATION_DATABASE_URL

    s = get_settings()
    assert s.database_dsn.startswith("postgresql://gap_app:")
    assert s.migration_dsn == LOCAL_MIGRATION_DATABASE_URL
    assert "gap_app" not in s.migration_dsn


def test_migration_url_falls_back_to_database_url_when_not_local_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:pw@db.example.test/x")
    assert get_settings().migration_dsn == "postgresql://app:pw@db.example.test/x"


def test_explicit_migration_url_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:pw@db.example.test/x")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://owner:pw@db.example.test/x")
    assert get_settings().migration_dsn == "postgresql://owner:pw@db.example.test/x"


def test_jwt_is_off_by_default():
    assert get_settings().jwt_enabled is False


def test_jwt_secret_needs_issuer_audience_and_length(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "s" * 40)
    with pytest.raises(SettingsError, match="JWT_ISSUER and JWT_AUDIENCE"):
        get_settings()
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_ISSUER", "https://i.example.test/")
    monkeypatch.setenv("JWT_AUDIENCE", "gap-api")
    assert get_settings().jwt_enabled is True
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(SettingsError, match="at least 32"):
        get_settings()


def test_jwt_secret_and_jwks_url_are_mutually_exclusive(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "s" * 40)
    monkeypatch.setenv("JWT_JWKS_URL", "https://i.example.test/jwks.json")
    monkeypatch.setenv("JWT_ISSUER", "i")
    monkeypatch.setenv("JWT_AUDIENCE", "a")
    with pytest.raises(SettingsError, match="only one of JWT_JWKS_URL and JWT_SECRET"):
        get_settings()


def test_settings_errors_never_echo_the_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "topsecretvalue")
    with pytest.raises(SettingsError) as exc:
        get_settings()
    assert "topsecretvalue" not in str(exc.value)


def test_receipt_signing_key_file(monkeypatch, tmp_path):
    import base64

    from evidence.receipts import keyring_from_settings

    sentinel = base64.b64encode(bytes(range(32))).decode()
    path = tmp_path / "receipt-signing.key"
    path.write_text(sentinel)
    path.chmod(0o600)
    monkeypatch.setenv("RECEIPT_SIGNING_KEY_FILE", str(path))
    settings = get_settings()
    assert settings.signing_key_text == sentinel
    assert sentinel not in repr(settings) + settings.model_dump_json()
    first_id = keyring_from_settings(settings).active_key_id
    get_settings.cache_clear()
    assert keyring_from_settings(get_settings()).active_key_id == first_id
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", KEY_TEXT)
    get_settings.cache_clear()
    with pytest.raises(SettingsError, match="only one") as conflict:
        get_settings()
    assert sentinel not in str(conflict.value)
    monkeypatch.delenv("RECEIPT_SIGNING_KEY")
    for fault in ("missing", "unreadable", "malformed", "symlink"):
        get_settings.cache_clear()
        if path.exists() or path.is_symlink():
            path.unlink()
        if fault == "unreadable":
            path.write_text(sentinel)
            path.chmod(0)
        elif fault == "malformed":
            path.write_text("private-file-sentinel!")
            path.chmod(0o600)
        elif fault == "symlink":
            actual = tmp_path / "actual"
            actual.write_text(sentinel)
            actual.chmod(0o600)
            path.symlink_to(actual)
        with pytest.raises(SettingsError) as error:
            get_settings()
        assert sentinel not in str(error.value) and "private-file-sentinel!" not in str(error.value)
    monkeypatch.delenv("RECEIPT_SIGNING_KEY_FILE")
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", sentinel)
    monkeypatch.setenv("RECEIPT_PREVIOUS_PUBLIC_KEYS", KEY_TEXT)
    get_settings.cache_clear()
    assert get_settings().previous_receipt_keys == [KEY_TEXT]
    assert keyring_from_settings(get_settings()).active_key_id == first_id

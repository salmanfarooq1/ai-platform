"""Unit tests for core/settings.py: validation and fail-fast behaviour."""
import importlib

import pytest

import config
from core.settings import LOCAL_DATABASE_URL, LOCAL_REDIS_URL, Settings, SettingsError, get_settings

pytestmark = pytest.mark.unit

_ENV_NAMES = [
    "MODE", "DATABASE_URL", "REDIS_URL", "LLM_MODEL", "EMBED_MODEL", "EMBEDDING_DIM",
    "RATE_LIMIT_REQUESTS", "CONFIDENCE_FLOOR", "OTEL_EXPORTER_OTLP_ENDPOINT", "RECEIPT_SIGNING_KEY",
    "RECEIPT_PREVIOUS_PUBLIC_KEYS", "METRICS_PUBLIC", "DECISION_RETENTION_DAYS",
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


def test_local_defaults_use_compose_services():
    s = get_settings()
    assert s.mode == "local"
    assert s.database_dsn == LOCAL_DATABASE_URL
    assert s.redis_dsn == LOCAL_REDIS_URL
    assert s.llm_model == "gemini/gemini-3.5-flash-lite"
    assert s.embed_model == "ollama/nomic-embed-text"
    assert s.embedding_dim == 768


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

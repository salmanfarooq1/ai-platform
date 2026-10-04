"""Validated application settings.

All configuration is read here, once, from the environment (and `.env.local` or
`.env`). A bad or missing value raises `SettingsError` at import time, so the
process never starts half-configured (strict rule 14). Secrets are referred to by
env var name only and never appear in error messages.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["local", "public-preview", "prod"]

# The app connects as the non-privileged role `gap_app` (row-level security applies to it).
# Migrations and the admin CLI connect as the owner role (MIGRATION_DATABASE_URL).
LOCAL_DATABASE_URL = "postgresql://gap_app:gap_app@localhost:5432/rag_platform"
LOCAL_MIGRATION_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/rag_platform"
LOCAL_REDIS_URL = "redis://localhost:6379"

_LLM_MODEL_DEFAULTS: dict[str, str] = {
    "local": "gemini/gemini-3.5-flash-lite",
    "public-preview": "gemini/gemini-3.5-flash-lite",
    "prod": "azure/gpt-4o",
}
_EMBED_MODEL_DEFAULTS: dict[str, str] = {
    "local": "ollama/nomic-embed-text",
    "public-preview": "gemini/gemini-embedding-001",
    "prod": "azure/text-embedding-3-small",
}


class SettingsError(ValueError):
    """Raised when configuration is missing or invalid."""


class Settings(BaseSettings):
    """Typed view of the environment. Field names equal env var names (case-insensitive)."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    mode: Mode = "local"

    # Required (no default) in public-preview and prod. Local falls back to Docker Compose.
    database_url: str | None = None
    # Owner role, used by Alembic and the admin CLI only. Falls back to DATABASE_URL.
    migration_database_url: str | None = None
    redis_url: str | None = None

    llm_model: str | None = None
    embed_model: str | None = None
    embedding_dim: int = Field(default=768, gt=0)

    azure_oai_base: str | None = None
    azure_oai_key: str | None = None
    groq_api_key: str | None = None

    max_query_length: int = Field(default=1000, gt=0)
    confidence_floor: float = Field(default=0.45, ge=0.0, le=1.0)

    rate_limit_requests: int = Field(default=60, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    daily_token_budget: int = Field(default=500_000, gt=0)

    # JWT verification (optional). Set JWT_JWKS_URL (asymmetric keys) or JWT_SECRET (HS256).
    jwt_jwks_url: str | None = None
    jwt_secret: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    frontend_url: str | None = None
    web_concurrency: int = Field(default=1, gt=0)
    log_level: str = "INFO"

    # OpenTelemetry: an exporter is created only when this is set.
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "ai-platform-api"

    @model_validator(mode="after")
    def _require_hosted_values(self) -> "Settings":
        if self.mode == "local":
            self.database_url = self.database_url or LOCAL_DATABASE_URL
            self.redis_url = self.redis_url or LOCAL_REDIS_URL
        else:
            missing = [
                name.upper()
                for name in ("database_url", "redis_url")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(f"{', '.join(missing)} must be set when MODE={self.mode}")
        if self.jwt_jwks_url and self.jwt_secret:
            raise ValueError("set only one of JWT_JWKS_URL and JWT_SECRET")
        if self.jwt_secret and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if (self.jwt_jwks_url or self.jwt_secret) and not (self.jwt_issuer and self.jwt_audience):
            raise ValueError("JWT_ISSUER and JWT_AUDIENCE must be set when JWT verification is configured")
        self.llm_model = self.llm_model or _LLM_MODEL_DEFAULTS[self.mode]
        self.embed_model = self.embed_model or _EMBED_MODEL_DEFAULTS[self.mode]
        return self

    @property
    def database_dsn(self) -> str:
        """Database URL, guaranteed set by validation."""
        if self.database_url is None:
            raise SettingsError("DATABASE_URL is not set")
        return self.database_url

    @property
    def migration_dsn(self) -> str:
        """Owner-role URL for migrations and admin tools. Local mode defaults to the compose superuser."""
        if self.migration_database_url:
            return self.migration_database_url
        if self.mode == "local" and self.database_url == LOCAL_DATABASE_URL:
            return LOCAL_MIGRATION_DATABASE_URL
        return self.database_dsn

    @property
    def jwt_enabled(self) -> bool:
        return bool(self.jwt_jwks_url or self.jwt_secret)

    @property
    def redis_dsn(self) -> str:
        if self.redis_url is None:
            raise SettingsError("REDIS_URL is not set")
        return self.redis_url


def _load_env_files() -> None:
    """Load `.env.local` if present, otherwise `.env` (same precedence as before)."""
    env_local = Path(".env.local")
    if env_local.exists():
        load_dotenv(dotenv_path=".env.local", override=True)
    else:
        load_dotenv()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build and cache the settings. Raises SettingsError with a readable message."""
    _load_env_files()
    try:
        return Settings()
    except ValidationError as exc:
        lines = []
        for err in exc.errors():
            loc = ".".join(str(p).upper() for p in err["loc"]) or "settings"
            msg = str(err["msg"]).removeprefix("Value error, ")
            lines.append(f"  - {loc}: {msg}" if loc != "settings" else f"  - {msg}")
        raise SettingsError("Invalid configuration:\n" + "\n".join(lines)) from None

"""Validated application settings.

All configuration is read here, once, from the environment (and `.env.local` or
`.env`). A bad or missing value raises `SettingsError` at import time, so the
process never starts half-configured (strict rule 14). Secrets are referred to by
env var name only and never appear in error messages.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from dotenv import load_dotenv
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
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


def _check_key_text(text: str) -> None:
    """Base64 text of 32 bytes. Never echoes the text."""
    import base64
    import binascii

    try:
        raw = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("not valid base64") from None
    if len(raw) != 32:
        raise ValueError("an Ed25519 key is 32 bytes")


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
    # Ordered, comma separated fallbacks tried when the primary embedding model fails (Sprint 006). A fallback
    # whose vectors have another width than EMBEDDING_DIM is refused. Empty by default: no provider is invented.
    embed_fallback_models: str | None = None

    # Object store adapter (ports/objects.py): `local` writes under OBJECT_STORE_DIR, `s3` talks to an S3 API (R2, MinIO).
    object_store: Literal["local", "s3"] = "local"
    object_store_dir: str = "data/objects"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # Events and agent runs (Sprint 007, ADR-0008 and ADR-0009). The defaults are the durable adapters: the outbox
    # (decision and ingest events are written in the transaction that made them) and the queued runtime (an agent
    # run is a job that a worker executes). `inprocess` keeps both in the API process, for tests and tools.
    # `kafka` (Sprint 010, ADR-0008): the API still writes the outbox in the decision's transaction. The relay publishes the
    # rows to Kafka instead of the in-process bus. Kafka is never reached inside a request.
    event_bus: Literal["inprocess", "outbox", "kafka"] = "outbox"
    # Kafka (EVENT_BUS=kafka). SASL values come from the environment only and the password is never logged.
    kafka_bootstrap: str | None = None
    kafka_client_id: str = "gap-platform"
    kafka_group_id: str = "gap-platform"
    kafka_security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = "PLAINTEXT"
    kafka_sasl_mechanism: Literal["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"] | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: SecretStr | None = None
    # A consumer tries a message this many times, then sends it to `<topic>.dlq` and moves on.
    kafka_max_attempts: int = Field(default=5, gt=0)
    kafka_retry_backoff_seconds: float = Field(default=0.5, ge=0)
    # Short producer limits: the relay holds a row lock while it waits for the broker's acknowledgement.
    kafka_request_timeout_seconds: float = Field(default=10.0, gt=0)
    kafka_send_timeout_seconds: float = Field(default=15.0, gt=0)
    # `openshell` (Sprint 009): the worker runs each agent run inside an OpenShell sandbox. The API still queues the run
    # as a job, so status and the runs API are unchanged (ADR-0009).
    agent_runtime: Literal["inprocess", "queued", "openshell"] = "queued"
    # How long `/v1/agent/query` waits for the worker before it answers 202 with the execution id.
    agent_sync_wait_seconds: float = Field(default=25.0, gt=0)

    # Job queue and workers (`python -m workers`). A claimed job is held under a lease and renewed while it runs.
    job_lease_seconds: int = Field(default=60, gt=0)
    job_poll_interval_seconds: float = Field(default=0.5, gt=0)
    # How often a running job renews its lease and looks for a stop request.
    job_beat_interval_seconds: float = Field(default=1.0, gt=0)
    job_max_attempts: int = Field(default=5, gt=0)
    job_backoff_base_seconds: float = Field(default=2.0, ge=0)
    worker_concurrency: int = Field(default=1, gt=0)
    worker_health_file: str = "/tmp/worker-health"
    worker_shutdown_grace_seconds: float = Field(default=30.0, ge=0)
    # Outbox relay: how often it looks for unpublished events, how many it takes, and when it gives up on one.
    outbox_poll_interval_seconds: float = Field(default=1.0, gt=0)
    outbox_batch_size: int = Field(default=50, gt=0)
    outbox_max_attempts: int = Field(default=10, gt=0)
    # For one-process hosting (no separate worker service): run this many workers, and the relay, inside the API.
    embedded_workers: int = Field(default=0, ge=0)
    embedded_relay: bool = False

    # Sandboxed agent runs (AGENT_RUNTIME=openshell, ADR-0009). SANDBOX_GATEWAY_URL is the address of this API as the
    # sandbox sees it: the agent gets it as GATEWAY_URL, and it is the only host the sandbox may connect to.
    sandbox_gateway_url: str | None = None
    # OpenShell gateway (gRPC host:port). Unset: the driver uses the active gateway of the OpenShell CLI configuration.
    openshell_endpoint: str | None = None
    openshell_workspace: str = "default"
    openshell_image: str | None = None  # a sandbox image with python3; unset uses the OpenShell default image
    sandbox_cpu: str = "1"
    sandbox_memory: str = "512Mi"
    sandbox_wall_seconds: int = Field(default=300, gt=0, le=3600)
    sandbox_work_dir: str = "/sandbox/work"
    # System paths the sandbox may read so python3 can start. Nothing else outside the work directory is readable.
    sandbox_read_only_paths: str = "/usr,/lib,/lib64,/bin,/sbin"
    # The executables that may open the sandbox's one network route (real paths or globs, comma separated). The agent is a
    # python3 script, so this lists the interpreter. OpenShell names a process by the real path of its executable.
    sandbox_network_binaries: str = "/usr/bin/python3*"

    azure_oai_base: str | None = None
    azure_oai_key: str | None = None
    groq_api_key: str | None = None

    max_query_length: int = Field(default=1000, gt=0)
    confidence_floor: float = Field(default=0.45, ge=0.0, le=1.0)

    rate_limit_requests: int = Field(default=60, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    daily_token_budget: int = Field(default=500_000, gt=0)
    # Daily cost cap per tenant in USD (Sprint 008). A tenant policy may set a lower cap, never a higher one.
    daily_cost_cap_usd: float = Field(default=10.0, gt=0)

    # Audit receipts (ADR-0012). RECEIPT_SIGNING_KEY is an Ed25519 private key, base64 of its 32 raw bytes. It is
    # required in public-preview and prod; local mode makes a throwaway key at startup. The previous public keys
    # (comma separated, base64) stay listed after a rotation so older receipts still verify.
    receipt_signing_key: SecretStr | None = None
    receipt_previous_public_keys: str | None = None

    # Retention (Q7, ADR-0012): how long decision records are kept. A tenant may override it (`set-retention`).
    decision_retention_days: int = Field(default=90, ge=30)  # the purge function floors at 30 days too
    purge_batch_size: int = Field(default=1000, gt=0)
    # How often a worker looks for tenants with expired records and queues a `purge_decisions` job (one a day per
    # tenant). 0 turns the scheduler off.
    retention_schedule_interval_seconds: float = Field(default=3600.0, ge=0)

    # Metrics (Sprint 008). `/metrics` is open when this is true and needs the `admin` scope when it is false. The
    # default is true in local and false elsewhere. WORKER_METRICS_PORT serves the worker's own series (0 is off).
    metrics_public: bool | None = None
    worker_metrics_port: int = Field(default=0, ge=0, le=65535)
    # A link the Trust page shows when the observability profile is running (for example http://localhost:3000).
    grafana_url: str | None = None

    # JWT verification (optional). Set JWT_JWKS_URL (asymmetric keys) or JWT_SECRET (HS256).
    jwt_jwks_url: str | None = None
    jwt_secret: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    frontend_url: str | None = None
    # Web edge: the principal a public-preview visitor gets a read-only session for. A principal id, never a key.
    preview_principal_id: UUID | None = None
    web_concurrency: int = Field(default=1, gt=0)
    log_level: str = "INFO"

    # OpenTelemetry: an exporter is created only when this is set.
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "ai-platform-api"

    @field_validator("preview_principal_id", mode="before")
    @classmethod
    def _blank_preview_principal_is_unset(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
        if self.preview_principal_id is not None and self.mode == "prod":
            raise ValueError("PREVIEW_PRINCIPAL_ID must not be set when MODE=prod (preview sessions are for local and public-preview)")
        if self.agent_runtime == "openshell":
            if not self.sandbox_gateway_url:
                raise ValueError("SANDBOX_GATEWAY_URL must be set when AGENT_RUNTIME=openshell")
            if self.sandbox_egress() is None:
                raise ValueError("SANDBOX_GATEWAY_URL must be an http or https URL with a host")
        if not self.sandbox_work_dir.startswith("/") or self.sandbox_work_dir.rstrip("/") == "":
            raise ValueError("SANDBOX_WORK_DIR must be an absolute path other than /")
        if not self.sandbox_network_binaries_list or any(not p.startswith("/") for p in self.sandbox_network_binaries_list):
            raise ValueError("SANDBOX_NETWORK_BINARIES must list at least one absolute path or glob")
        if any(not p.startswith("/") or p.rstrip("/") == "" for p in self.sandbox_read_only):
            raise ValueError("SANDBOX_READ_ONLY_PATHS must be absolute paths other than /")
        if self.event_bus == "kafka" and not (self.kafka_bootstrap or "").strip():
            raise ValueError("KAFKA_BOOTSTRAP must be set when EVENT_BUS=kafka")
        if self.kafka_security_protocol.startswith("SASL"):
            missing_sasl = [
                name.upper() for name in ("kafka_sasl_mechanism", "kafka_sasl_username", "kafka_sasl_password")
                if not getattr(self, name)
            ]
            if missing_sasl:
                raise ValueError(f"{', '.join(missing_sasl)} must be set when KAFKA_SECURITY_PROTOCOL={self.kafka_security_protocol}")
        if self.object_store == "s3":
            missing_s3 = [
                name.upper()
                for name in ("s3_endpoint_url", "s3_bucket", "s3_access_key_id", "s3_secret_access_key")
                if not getattr(self, name)
            ]
            if missing_s3:
                raise ValueError(f"{', '.join(missing_s3)} must be set when OBJECT_STORE=s3")
        if self.mode != "local" and not self.signing_key_text:
            raise ValueError(f"RECEIPT_SIGNING_KEY must be set when MODE={self.mode}")
        for name in ("receipt_signing_key", "receipt_previous_public_keys"):
            value = getattr(self, name)
            for part in (value.get_secret_value() if isinstance(value, SecretStr) else str(value or "")).split(","):
                if part.strip():
                    try:
                        _check_key_text(part)
                    except ValueError as exc:
                        raise ValueError(f"{name.upper()} is not valid: {exc}") from None
        if self.metrics_public is None:
            self.metrics_public = self.mode == "local"
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

    def sandbox_egress(self) -> tuple[str, int] | None:
        """(host, port) of `SANDBOX_GATEWAY_URL`: the one place a sandbox may connect to. None if it is not a usable URL."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(self.sandbox_gateway_url or "")
            host, port = parsed.hostname, parsed.port
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not host:
            return None
        return host, port or (443 if parsed.scheme == "https" else 80)

    @property
    def sandbox_read_only(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.sandbox_read_only_paths.split(",") if p.strip())

    @property
    def sandbox_network_binaries_list(self) -> tuple[str, ...]:
        return tuple(p.strip() for p in self.sandbox_network_binaries.split(",") if p.strip())

    @property
    def embed_fallbacks(self) -> list[str]:
        """The ordered fallback embedding models (blank entries dropped)."""
        return [m.strip() for m in (self.embed_fallback_models or "").split(",") if m.strip()]

    @property
    def signing_key_text(self) -> str:
        """The signing key text, or an empty string. Read it here and nowhere else, so it is never printed by accident."""
        return self.receipt_signing_key.get_secret_value().strip() if self.receipt_signing_key else ""

    @property
    def previous_receipt_keys(self) -> list[str]:
        """The earlier public keys (base64), blank entries dropped."""
        return [k.strip() for k in (self.receipt_previous_public_keys or "").split(",") if k.strip()]

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

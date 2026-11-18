"""Validated application settings.

All configuration is read here, once, from the environment (and `.env.local` or
`.env`). A bad or missing value raises `SettingsError` at import time, so the
process never starts half-configured (strict rule 14). Secrets are referred to by
env var name only and never appear in error messages.
"""
import os
import stat
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlsplit
from uuid import UUID

from dotenv import load_dotenv
from pydantic import Field, PrivateAttr, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["local", "public-preview", "prod"]
DeployShape = Literal["single_tenant", "multi_tenant"]

# The app connects as the non-privileged role `gap_app` (row-level security applies to it).
# Migrations and the admin CLI connect as the owner role (MIGRATION_DATABASE_URL).
LOCAL_DATABASE_URL = "postgresql://gap_app:gap_app@localhost:5432/rag_platform"
LOCAL_MIGRATION_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/rag_platform"
LOCAL_REDIS_URL = "redis://localhost:6379"

_LLM_MODEL_DEFAULTS: dict[str, str] = {
    "local": "ollama/qwen3:4b-instruct-2507-q4_K_M",
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


@contextmanager
def secret_directory(path: Path) -> Iterator[int]:
    """Open every path component without following links; caller owns the final fd temporarily."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        # Keep `..` until traversal: normalizing first can hide a symlink/.. component.
        absolute = path if path.is_absolute() else Path.cwd() / path
        for component in absolute.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_secret_at(directory: int, name: str, *, owned: bool = False) -> str:
    """Read a small private regular file. No links, devices, partial reads, or secret-bearing errors.

    Container root may read a bind-mounted host-owned file; operator lifecycle calls
    additionally require ownership by their uid.
    """
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1 or (owned and info.st_uid != os.getuid())):
            raise ValueError("unsafe secret file")
        with os.fdopen(fd, "r", encoding="ascii", closefd=False) as stream:
            value = stream.read(257)
        if not value or len(value) > 256:
            raise ValueError("invalid secret file")
        return value
    finally:
        os.close(fd)


def read_signing_key_file(path: str) -> str:
    """Load validated private key text without revealing the path or its contents on failure."""
    try:
        with secret_directory(Path(path).parent) as directory:
            text = read_secret_at(directory, Path(path).name)
        _check_key_text(text)
        return text.strip()
    except (OSError, ValueError):
        raise ValueError("RECEIPT_SIGNING_KEY_FILE is missing, unreadable, unsafe or malformed") from None


class Settings(BaseSettings):
    """Typed view of the environment. Field names equal env var names (case-insensitive)."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False, hide_input_in_errors=True)
    _file_signing_key: SecretStr | None = PrivateAttr(default=None)

    deploy_shape: DeployShape = Field(
        default="single_tenant", description="Tenant deployment shape: one tenant by default, or `multi_tenant` for multiple tenants.",
    )
    enabled_modules: str = Field(
        default="all", description="Comma-separated enabled modules, or `all`; the gateway module is always required.",
    )

    mode: Mode = Field(
        default="local",
        description="Deployment mode: `local`, `public-preview` or `prod`. It picks the model defaults and which values are required.",
    )

    database_url: str | None = Field(
        default=None,
        description="Postgres URL the app connects with. It must be a role that is neither superuser nor BYPASSRLS. Required outside local mode; local mode defaults to the `gap_app` role of the compose Postgres.",
        json_schema_extra={"secret": True},
    )
    migration_database_url: str | None = Field(
        default=None,
        description="Postgres URL of the owner role, used by Alembic and `scripts/admin/identity.py`. Falls back to `DATABASE_URL`; local mode defaults to the compose superuser.",
        json_schema_extra={"secret": True},
    )
    redis_url: str | None = Field(
        default=None,
        description="Valkey or Redis URL. The server needs a search module (valkey-search). Required outside local mode; local mode defaults to `redis://localhost:6379`.",
        json_schema_extra={"secret": True},
    )

    llm_model: str | None = Field(
        default=None,
        description="LiteLLM model name for chat and completions. Default by mode: `ollama/qwen3:4b-instruct-2507-q4_K_M` (local), `gemini/gemini-3.5-flash-lite` (public-preview), `azure/gpt-4o` (prod).",
    )
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        description="Ollama HTTP endpoint shared by the local model catalog and legacy completions. Set OLLAMA_BASE_URL to override it; SDK environment variables do not select this endpoint.",
    )

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("ollama_base_url must be an HTTP or HTTPS endpoint")
        return value.rstrip("/")

    verifier_model: str | None = Field(
        default=None,
        description="Model alias used for agent answer verification. Defaults to the mode's chat model; a hosted verifier is subject to the same model policy checks.",
    )
    deploy_region: str | None = Field(
        default=None,
        description="Deployment processing region used as the identity region for local models and required when a hosted model provider is configured.",
    )
    embed_model: str | None = Field(
        default=None,
        description="LiteLLM model name for embeddings. Default by mode: `ollama/nomic-embed-text` (local), `gemini/gemini-embedding-001` (public-preview), `azure/text-embedding-3-small` (prod). Chunks record the model that made them, and search ignores chunks of another model.",
    )
    embedding_dim: int = Field(
        default=768, gt=0,
        description="Width of every stored vector. It must match the `vector` column of the schema.",
    )
    embed_fallback_models: str | None = Field(
        default=None,
        description="Comma separated embedding models tried in order when the primary fails. A model whose vectors have another width than `EMBEDDING_DIM` is refused. Empty means no fallback.",
    )
    model_allowed_hosts: str = Field(
        default="",
        description="Comma-separated hosted model endpoint hostnames allowed by the application. This application check is not network egress control; network egress control is Sprint 016.",
    )
    model_max_concurrent_per_tenant: int = Field(
        default=8, ge=1, description="Maximum simultaneous model calls allowed per tenant.",
    )
    model_call_timeout_seconds: float = Field(
        default=60.0, gt=0, description="Maximum duration of one physical model call, in seconds.",
    )
    model_lease_ttl_margin_seconds: float = Field(
        default=10.0, gt=0, description="Extra life for a model concurrency lease beyond the call timeout, in seconds.",
    )
    model_breaker_failure_threshold: int = Field(
        default=5, ge=1, description="Consecutive provider failures before a model route breaker opens.",
    )
    model_breaker_open_seconds: float = Field(
        default=30.0, gt=0, description="Seconds a model route breaker stays open before one trial is allowed.",
    )

    object_store: Literal["local", "s3"] = Field(
        default="local",
        description="Object store adapter for raw uploads: `local` writes files under `OBJECT_STORE_DIR`, `s3` uses an S3 API (R2, MinIO, S3).",
    )
    object_store_dir: str = Field(default="data/objects", description="Directory of the `local` object store.")
    s3_endpoint_url: str | None = Field(default=None, description="S3 API endpoint. Required when `OBJECT_STORE=s3`.")
    s3_bucket: str | None = Field(default=None, description="S3 bucket name. Required when `OBJECT_STORE=s3`.")
    s3_region: str = Field(default="auto", description="S3 region.")
    s3_access_key_id: str | None = Field(
        default=None, description="S3 access key id. Required when `OBJECT_STORE=s3`.",
        json_schema_extra={"secret": True},
    )
    s3_secret_access_key: str | None = Field(
        default=None, description="S3 secret access key. Required when `OBJECT_STORE=s3`.",
        json_schema_extra={"secret": True},
    )

    event_bus: Literal["inprocess", "outbox", "kafka"] = Field(
        default="outbox",
        description="Event bus: `outbox` writes events in the transaction of the change and a relay publishes them, `kafka` makes the relay publish to Kafka, `inprocess` keeps events in the API process (tests and tools).",
    )
    kafka_bootstrap: str | None = Field(
        default=None, description="Comma separated `host:port` list of Kafka brokers. Required when `EVENT_BUS=kafka`.",
    )
    kafka_client_id: str = Field(default="gap-platform", description="Kafka client id.")
    kafka_group_id: str = Field(default="gap-platform", description="Kafka consumer group.")
    kafka_security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = Field(
        default="PLAINTEXT", description="Kafka security protocol. A SASL protocol needs the three `KAFKA_SASL_*` values.",
    )
    kafka_sasl_mechanism: Literal["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"] | None = Field(
        default=None, description="SASL mechanism. Required with a SASL protocol.",
    )
    kafka_sasl_username: str | None = Field(default=None, description="SASL user name. Required with a SASL protocol.")
    kafka_sasl_password: SecretStr | None = Field(
        default=None, description="SASL password. Required with a SASL protocol. Set it in the environment only.",
        json_schema_extra={"secret": True},
    )
    kafka_max_attempts: int = Field(
        default=5, gt=0, description="Tries a consumer makes for a message before it goes to `<topic>.dlq`.",
    )
    kafka_retry_backoff_seconds: float = Field(default=0.5, ge=0, description="Pause between consumer tries, in seconds.")
    kafka_request_timeout_seconds: float = Field(
        default=10.0, gt=0, description="Limit of one request to the broker, in seconds.",
    )
    kafka_send_timeout_seconds: float = Field(
        default=15.0, gt=0,
        description="Limit of one send with its acknowledgement, in seconds. The relay holds a row lock meanwhile, so keep it short.",
    )
    agent_runtime: Literal["inprocess", "queued", "openshell"] = Field(
        default="queued",
        description="Agent runtime: `queued` runs each agent run as a job in a worker, `openshell` runs it in an OpenShell sandbox started by a worker, `inprocess` runs it in the API process.",
    )
    agent_sync_wait_seconds: float = Field(
        default=25.0, gt=0,
        description="How long `POST /v1/agent/query` waits for the worker before it answers 202 with the execution id.",
    )

    job_lease_seconds: int = Field(
        default=60, gt=0, description="Lease of a claimed job, in seconds. A worker renews it while the job runs; a lost lease lets another worker take the job.",
    )
    job_poll_interval_seconds: float = Field(default=0.5, gt=0, description="How often an idle worker looks for a job, in seconds.")
    job_beat_interval_seconds: float = Field(
        default=1.0, gt=0, description="How often a running job renews its lease and looks for a stop request, in seconds.",
    )
    job_max_attempts: int = Field(default=5, gt=0, description="Tries a job gets before it ends `dead`.")
    job_backoff_base_seconds: float = Field(
        default=2.0, ge=0, description="Base of the retry delay in seconds. The delay is the base times 2 to the power of the attempts, with jitter.",
    )
    worker_concurrency: int = Field(default=1, gt=0, description="Jobs one worker process runs at the same time.")
    worker_health_file: str = Field(
        default="/tmp/worker-health", description="File a worker touches while it is healthy. The compose health check reads its age.",
    )
    worker_shutdown_grace_seconds: float = Field(
        default=30.0, ge=0, description="How long a worker waits for running jobs after SIGTERM, in seconds.",
    )
    outbox_poll_interval_seconds: float = Field(
        default=1.0, gt=0, description="How often the outbox relay looks for unpublished events, in seconds.",
    )
    outbox_batch_size: int = Field(default=50, gt=0, description="Events the outbox relay takes in one pass.")
    outbox_max_attempts: int = Field(
        default=10, gt=0, description="Tries the relay makes for one event before it leaves the row for an operator.",
    )
    embedded_workers: int = Field(
        default=0, ge=0, description="Number of workers to run inside the API process. 0 means none. For hosts that run one container.",
    )
    embedded_relay: bool = Field(default=False, description="Run the outbox relay inside the API process.")

    sandbox_gateway_url: str | None = Field(
        default=None,
        description="Address of this API as the sandbox sees it. It is the only host the sandbox may connect to, and it must not be loopback. Required when `AGENT_RUNTIME=openshell`.",
    )
    openshell_endpoint: str | None = Field(
        default=None,
        description="OpenShell gateway `host:port`. Unset uses the active gateway of the OpenShell CLI configuration.",
    )
    openshell_workspace: str = Field(default="default", description="OpenShell workspace name.")
    openshell_image: str | None = Field(
        default=None,
        description="Workload image of the sandbox. It needs `python3`, a user named `sandbox` and the work directory. Unset uses the OpenShell default image, which has no `python3`.",
    )
    sandbox_cpu: str = Field(default="1", description="CPU limit of a sandbox, for example `1` or `500m`.")
    sandbox_memory: str = Field(default="512Mi", description="Memory limit of a sandbox, for example `512Mi`.")
    sandbox_wall_seconds: int = Field(
        default=300, gt=0, le=3600,
        description="Wall-clock limit of a sandboxed run, in seconds. It is also the life of the run token, plus a minute.",
    )
    sandbox_work_dir: str = Field(
        default="/sandbox/work", description="The one directory a sandbox may write. It must exist in the image. An absolute path other than `/`.",
    )
    sandbox_read_only_paths: str = Field(
        default="/usr,/lib,/lib64,/bin,/sbin",
        description="Comma separated system paths a sandbox may read so `python3` can start. Nothing else outside the work directory is readable.",
    )
    sandbox_network_binaries: str = Field(
        default="/usr/bin/python3*",
        description="Comma separated real paths or globs of the executables that may open the sandbox's one network route. A symlink does not match.",
    )

    azure_oai_base: str | None = Field(default=None, description="Azure OpenAI endpoint. Used by `azure/...` models.")
    azure_oai_key: str | None = Field(
        default=None, description="Azure OpenAI key. Used by `azure/...` models.", json_schema_extra={"secret": True},
    )
    groq_api_key: str | None = Field(
        default=None, description="Groq API key. Used only when `LLM_MODEL` names a Groq model.", json_schema_extra={"secret": True},
    )

    max_query_length: int = Field(default=1000, gt=0, description="Longest question the input guardrail accepts, in characters.")
    confidence_floor: float = Field(
        default=0.45, ge=0.0, le=1.0, description="Retrieval score below which the output guardrail flags an answer.",
    )

    rate_limit_requests: int = Field(default=60, gt=0, description="Requests one principal may make in a rate-limit window.")
    rate_limit_window_seconds: int = Field(default=60, gt=0, description="Length of the rate-limit window, in seconds.")
    daily_token_budget: int = Field(default=500_000, gt=0, description="Tokens a tenant may use per UTC day.")
    daily_cost_cap_usd: float = Field(
        default=10.0, gt=0, description="Cost a tenant may spend per UTC day, in USD. A tenant policy may set a lower cap, never a higher one.",
    )

    receipt_signing_key: SecretStr | None = Field(
        default=None,
        description="Ed25519 private key for receipts: base64 of 32 raw bytes. Set this or RECEIPT_SIGNING_KEY_FILE in `public-preview` and `prod`; local mode with neither makes a throwaway key. Set the same key in the API and every worker.",
        json_schema_extra={"secret": True},
    )
    receipt_signing_key_file: str | None = Field(
        default=None,
        description="Path to a read-only mounted 0600 file containing a base64 Ed25519 private key (32 raw bytes). Rejects symlinks and unsafe files. Mutually exclusive with RECEIPT_SIGNING_KEY; API and worker must mount the same file. Back up the private file separately from data.",
    )
    receipt_previous_public_keys: str | None = Field(
        default=None,
        description="Comma separated base64 public keys of earlier signing keys. They stay listed after a rotation so older receipts still verify.",
    )

    decision_retention_days: int = Field(
        default=90, ge=30,
        description="Days decision records are kept. A tenant may set its own value. The minimum is 30.",
    )
    purge_batch_size: int = Field(default=1000, gt=0, description="Decision rows one purge step deletes.")
    retention_schedule_interval_seconds: float = Field(
        default=3600.0, ge=0,
        description="How often a worker looks for tenants with expired records and queues a purge job (one a day per tenant). 0 turns the scheduler off.",
    )

    metrics_public: bool | None = Field(
        default=None,
        description="`/metrics` is open when true and needs the `admin` scope when false. Unset means true in local mode and false elsewhere.",
    )
    worker_metrics_port: int = Field(
        default=0, ge=0, le=65535, description="Port where a worker serves its own metrics. 0 turns it off.",
    )
    grafana_url: str | None = Field(
        default=None, description="Link the Trust page shows when the observability profile runs, for example `http://localhost:3000`.",
    )

    jwt_jwks_url: str | None = Field(
        default=None, description="JWKS URL for JWT verification with asymmetric keys. Set only one of this and `JWT_SECRET`.",
    )
    jwt_secret: str | None = Field(
        default=None,
        description="HS256 secret for JWT verification, at least 32 characters. Set only one of this and `JWT_JWKS_URL`.",
        json_schema_extra={"secret": True},
    )
    jwt_issuer: str | None = Field(default=None, description="Expected JWT issuer. Required when JWT verification is on.")
    jwt_audience: str | None = Field(default=None, description="Expected JWT audience. Required when JWT verification is on.")

    frontend_url: str | None = Field(default=None, description="Extra origin allowed by CORS. The Vite dev and preview ports on localhost are always allowed.")
    preview_principal_id: UUID | None = Field(
        default=None,
        description="Principal id (a UUID, never a key) that a visitor gets a read-only session for at `POST /v1/session/preview`. Used only when `MODE=public-preview`, and not allowed when `MODE=prod`.",
    )
    web_concurrency: int = Field(default=1, gt=0, description="Number of API worker processes you run. The API logs the total database connection budget from it.")
    log_level: str = Field(default="INFO", description="Log level of the JSON logs.")

    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, description="OTLP endpoint for traces. Unset means no exporter and no background thread.",
    )
    otel_service_name: str = Field(default="ai-platform-api", description="Service name on exported traces.")

    @field_validator("enabled_modules")
    @classmethod
    def _validate_enabled_modules(cls, value: str) -> str:
        from core.modules import parse_enabled_modules

        enabled = parse_enabled_modules(value)
        return "all" if value.strip() == "all" else ",".join(sorted(enabled))

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
        if self.receipt_signing_key_file is not None:
            if self.receipt_signing_key is not None:
                raise ValueError("set only one of RECEIPT_SIGNING_KEY and RECEIPT_SIGNING_KEY_FILE")
            self._file_signing_key = SecretStr(read_signing_key_file(self.receipt_signing_key_file))
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
        if self.verifier_model is None:
            self.verifier_model = self.llm_model
        from core.models_files import PROVIDER_PREFIX_TO_KEY, load_provider_register

        provider_regions = {
            details["region"]
            for provider in load_provider_register().values()
            for details in provider.processing_scopes.values()
            if details.get("region") not in (None, "unknown")
        }
        if self.deploy_region and self.deploy_region not in provider_regions:
            raise ValueError("DEPLOY_REGION must match a region name in providers.register.toml")
        aliases = [self.llm_model, self.embed_model, self.verifier_model, *self.embed_fallbacks]
        configured_hosted = []
        for alias in aliases:
            prefix = alias.split("/", 1)[0] if alias else ""
            if prefix in PROVIDER_PREFIX_TO_KEY and prefix != "ollama":
                configured_hosted.append(alias)
        if configured_hosted and not self.deploy_region:
            raise ValueError("DEPLOY_REGION must be set when a hosted model provider is configured")
        if "agents" in self.enabled_module_names and not self.verifier_model:
            raise ValueError("VERIFIER_MODEL must be set when the Agents module is enabled")
        if self.deploy_region:
            for alias in configured_hosted:
                prefix, _, model_id = alias.partition("/")
                if prefix == "bedrock":
                    minimum = next((region for region in ("us", "eu", "apac", "global") if model_id.startswith(region + ".")), None)
                    if minimum and self.deploy_region not in {minimum, "global"}:
                        raise ValueError(f"DEPLOY_REGION is narrower than the Bedrock model scope required by {minimum}.")
        return self

    @property
    def enabled_module_names(self) -> frozenset[str]:
        """Enabled module set, already validated against the platform registry."""
        from core.modules import parse_enabled_modules

        return parse_enabled_modules(self.enabled_modules)

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
    def model_allowed_host_list(self) -> list[str]:
        return [host.strip().lower() for host in self.model_allowed_hosts.split(",") if host.strip()]

    @property
    def signing_key_text(self) -> str:
        """The signing key text, or an empty string. Read it here and nowhere else, so it is never printed by accident."""
        key = self._file_signing_key if self.receipt_signing_key_file is not None else self.receipt_signing_key
        return key.get_secret_value().strip() if key else ""

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
    """Load the selected file without replacing real environment values."""
    env_local = Path(".env.local")
    if env_local.exists():
        load_dotenv(dotenv_path=".env.local", override=False)
    else:
        load_dotenv(override=False)


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

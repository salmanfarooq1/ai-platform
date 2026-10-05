"""The composition root: builds the one `Adapters` bundle from `Settings` at startup (ADR-0005).

Routes, the gateway, the agent and the MCP tools receive ports from `app.state.adapters`, never SDKs. Swapping a
provider is a change here (and in settings). Tests pass `overrides` to put fakes behind the same ports, so the
app they exercise is built by this same function.
"""
from collections.abc import Mapping
from typing import Any

import config
from adapters.inprocess_events import InProcessEventBus
from adapters.inprocess_runtime import InProcessAgentRuntime
from adapters.job_runtime import JobAgentRuntime
from adapters.litellm_chat import LitellmChat
from adapters.litellm_embeddings import LitellmEmbeddings
from adapters.litellm_llm import LitellmLLM
from adapters.local_object_store import LocalObjectStore
from adapters.openshell_driver import OpenShellSdkDriver
from adapters.openshell_runtime import OpenShellAgentRuntime, SandboxConfig
from adapters.pg_knowledge import PgKnowledgeStore
from adapters.pg_outbox_events import OutboxEventBus
from adapters.redis_cache import RedisCache
from adapters.s3_object_store import S3ObjectStore
from core.database.tenant import DbPool
from core.settings import Settings
from gateway.context import context_to_payload
from ports import Adapters, AgentRuntime, EgressRule, EventBus, ObjectStore, Runner, SandboxDriver, SandboxLimits

PORT_NAMES = ("llm", "chat", "embeddings", "knowledge", "cache", "objects", "events", "runtime")


def _object_store(settings: Settings) -> ObjectStore:
    if settings.object_store == "s3":
        # Settings validation guarantees these are set when OBJECT_STORE=s3.
        return S3ObjectStore.from_settings(
            endpoint_url=str(settings.s3_endpoint_url), bucket=str(settings.s3_bucket),
            access_key_id=str(settings.s3_access_key_id), secret_access_key=str(settings.s3_secret_access_key),
            region=settings.s3_region,
        )
    return LocalObjectStore(settings.object_store_dir)


def build_local_runtime(
    settings: Settings, *, runner: Runner | None, pool: DbPool, sandbox_driver: SandboxDriver | None = None,
) -> AgentRuntime:
    """The runtime that executes a run where it is claimed: inside a worker (or the API, for `inprocess`).

    `AGENT_RUNTIME=openshell` runs each run in a sandbox (`adapters/openshell_runtime.py`); every other value runs it as
    a task of this process. A test passes `sandbox_driver` to put a fake sandbox behind the same runtime.
    """
    if settings.agent_runtime != "openshell":
        return InProcessAgentRuntime(runner)
    egress = settings.sandbox_egress()
    if egress is None:  # settings validation guarantees it; this keeps the type honest
        raise ValueError("SANDBOX_GATEWAY_URL is not a usable URL")
    driver = sandbox_driver or OpenShellSdkDriver(
        endpoint=settings.openshell_endpoint, workspace=settings.openshell_workspace, image=settings.openshell_image,
    )
    return OpenShellAgentRuntime(driver, pool, SandboxConfig(
        gateway_url=str(settings.sandbox_gateway_url), egress=EgressRule(*egress),
        limits=SandboxLimits(settings.sandbox_cpu, settings.sandbox_memory, settings.sandbox_wall_seconds),
        work_dir=settings.sandbox_work_dir, read_only=settings.sandbox_read_only, network_binaries=settings.sandbox_network_binaries_list,
    ))


def build_adapters(
    settings: Settings,
    *,
    pool: DbPool | None = None,
    agent_runner: Runner | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Adapters:
    """One adapter per port. An override replaces that port's adapter and the real one is never built."""
    overrides = dict(overrides or {})
    unknown = set(overrides) - set(PORT_NAMES)
    if unknown:
        raise ValueError(f"unknown adapter override(s): {', '.join(sorted(unknown))}")

    def pick(name: str, build: Any) -> Any:
        return overrides[name] if name in overrides else build()

    def knowledge() -> PgKnowledgeStore:
        if pool is None:
            raise ValueError("the Postgres knowledge store needs a pool")
        return PgKnowledgeStore(pool)

    def events() -> EventBus:
        if settings.event_bus == "outbox":
            if pool is None:
                raise ValueError("the Postgres outbox event bus needs a pool")
            return OutboxEventBus(pool)
        return InProcessEventBus()

    def runtime() -> AgentRuntime:
        # `openshell` queues the run like `queued` does: the worker is where the sandbox runs (build_local_runtime).
        if settings.agent_runtime in ("queued", "openshell"):
            if pool is None:
                raise ValueError("the queued agent runtime needs a pool")
            return JobAgentRuntime(pool, serialize_context=context_to_payload)
        return InProcessAgentRuntime(agent_runner)

    return Adapters(
        llm=pick("llm", lambda: LitellmLLM(config.MODEL_PRICING)),
        chat=pick("chat", lambda: LitellmChat(str(settings.llm_model))),
        embeddings=pick("embeddings", lambda: LitellmEmbeddings(
            str(settings.embed_model), settings.embedding_dim, settings.embed_fallbacks)),
        knowledge=pick("knowledge", knowledge),
        cache=pick("cache", lambda: RedisCache(settings.redis_dsn, settings.embedding_dim)),
        objects=pick("objects", lambda: _object_store(settings)),
        events=pick("events", events),
        runtime=pick("runtime", runtime),
    )

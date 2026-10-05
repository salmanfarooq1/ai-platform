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
from adapters.litellm_chat import LitellmChat
from adapters.litellm_embeddings import LitellmEmbeddings
from adapters.litellm_llm import LitellmLLM
from adapters.local_object_store import LocalObjectStore
from adapters.pg_knowledge import PgKnowledgeStore
from adapters.redis_cache import RedisCache
from adapters.s3_object_store import S3ObjectStore
from core.database.tenant import DbPool
from core.settings import Settings
from ports import Adapters, ObjectStore, Runner

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

    return Adapters(
        llm=pick("llm", lambda: LitellmLLM(config.MODEL_PRICING)),
        chat=pick("chat", lambda: LitellmChat(str(settings.llm_model))),
        embeddings=pick("embeddings", lambda: LitellmEmbeddings(
            str(settings.embed_model), settings.embedding_dim, settings.embed_fallbacks)),
        knowledge=pick("knowledge", knowledge),
        cache=pick("cache", lambda: RedisCache(settings.redis_dsn, settings.embedding_dim)),
        objects=pick("objects", lambda: _object_store(settings)),
        events=pick("events", InProcessEventBus),
        runtime=pick("runtime", lambda: InProcessAgentRuntime(agent_runner)),
    )

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Request

from api.dependencies import adapters_of
from api.models.schemas import HealthResponse
from api.services.cache import cache_health
from config import MODE
from ports import EmbeddingPort

router = APIRouter()
_start_time = time.time()

# We cache the LLM health check so we don't bombard the LLM every 30 seconds.
# If the LLM is healthy ("ok"), we trust that for 60 seconds.
# If it's failing, we check it more frequently (every 10 seconds) so we recover faster.
_embed_cache: dict[str, Any] = {"status": "unknown", "checked_at": 0.0}
_EMBED_OK_TTL = 60
_EMBED_FAIL_TTL = 10
_embed_lock = asyncio.Lock()

# Ollama unloads its models from memory when idle. If we ping it after an hour of silence,
# it takes a few seconds to "wake up" and load the model again.
# We set a retry delay so we don't accidentally report the API as "down" just because it was waking up.
_EMBED_PROBE_TIMEOUT = 8.0
_EMBED_COLD_START_RETRY_DELAY = 1.0


async def _probe_once(embeddings: EmbeddingPort) -> str:
    result = await asyncio.wait_for(
        embeddings.embed(["health check"]),
        timeout=_EMBED_PROBE_TIMEOUT,
    )
    return "ok" if result.vectors else "error: empty response"


async def _check_embedding(embeddings: EmbeddingPort) -> str:
    """Probe the embedding API, with a lock so concurrent /health requests
    arriving during the stale window do not all fire duplicate probes."""
    def _fresh(now: float) -> bool:
        ttl = _EMBED_OK_TTL if _embed_cache["status"] == "ok" else _EMBED_FAIL_TTL
        return now - _embed_cache["checked_at"] <= ttl

    if _fresh(time.time()):
        return _embed_cache["status"]

    async with _embed_lock:
        if _fresh(time.time()):  # another request may have refreshed it while we waited on the lock
            return _embed_cache["status"]

        try:
            status = await _probe_once(embeddings)
        except Exception:
            await asyncio.sleep(_EMBED_COLD_START_RETRY_DELAY)
            try:
                status = await _probe_once(embeddings)
            except Exception as e:
                status = f"error: {str(e)}"

        _embed_cache["status"] = status
        _embed_cache["checked_at"] = time.time()

    return _embed_cache["status"]


async def _stale_vectors(request: Request) -> int | None:
    """Chunks embedded with another model or dimension than the active one: search ignores them. None if unknown."""
    adapters = adapters_of(request)
    try:
        return await adapters.knowledge.count_stale_vectors(adapters.embeddings.active_model, adapters.embeddings.active_dim)
    except Exception:
        return None


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    try:
        async with request.app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    adapters = adapters_of(request)
    redis_status = await cache_health(adapters.cache)
    embed_status = await _check_embedding(adapters.embeddings)
    stale_vectors = await _stale_vectors(request)
    all_ok = all(s == "ok" for s in [db_status, redis_status, embed_status])

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        db=db_status,
        redis=redis_status,
        embedding=embed_status,
        version=request.app.version,
        mode=MODE,
        uptime_seconds=int(time.time() - _start_time),
        stale_vectors=stale_vectors,
    )

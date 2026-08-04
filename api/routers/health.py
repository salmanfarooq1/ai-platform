import asyncio
import time

from fastapi import APIRouter, Request

from api.models.schemas import HealthResponse
from api.services.cache import redis_health
from config import LLM_CONFIG, MODE

router = APIRouter()
_start_time = time.time()

# We cache the LLM health check so we don't bombard the LLM every 30 seconds.
# If the LLM is healthy ("ok"), we trust that for 60 seconds.
# If it's failing, we check it more frequently (every 10 seconds) so we recover faster.
_embed_cache = {"status": "unknown", "checked_at": 0.0}
_EMBED_OK_TTL = 60
_EMBED_FAIL_TTL = 10
_embed_lock = asyncio.Lock()

# Ollama unloads its models from memory when idle. If we ping it after an hour of silence,
# it takes a few seconds to "wake up" and load the model again.
# We set a retry delay so we don't accidentally report the API as "down" just because it was waking up.
_EMBED_PROBE_TIMEOUT = 8.0
_EMBED_COLD_START_RETRY_DELAY = 1.0


async def _probe_once() -> str:
    import litellm
    resp = await asyncio.wait_for(
        litellm.aembedding(model=LLM_CONFIG["embedding_model"], input=["health check"]),
        timeout=_EMBED_PROBE_TIMEOUT,
    )
    return "ok" if resp.data else "error: empty response"


async def _check_embedding() -> str:
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
            status = await _probe_once()
        except Exception:
            await asyncio.sleep(_EMBED_COLD_START_RETRY_DELAY)
            try:
                status = await _probe_once()
            except Exception as e:
                status = f"error: {str(e)}"

        _embed_cache["status"] = status
        _embed_cache["checked_at"] = time.time()

    return _embed_cache["status"]


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    try:
        async with request.app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    redis_status = await redis_health()
    embed_status = await _check_embedding()
    all_ok = all(s == "ok" for s in [db_status, redis_status, embed_status])

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        db=db_status,
        redis=redis_status,
        version="0.3.0",
        mode=MODE,
        uptime_seconds=int(time.time() - _start_time),
    )

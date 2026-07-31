import time

from fastapi import APIRouter, Request

from api.models.schemas import HealthResponse
from api.services.cache import redis_health
from config import LLM_CONFIG, MODE

router = APIRouter()

# Recorded at import time (process startup). Used to calculate uptime.
_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    # Check DB by acquiring a connection and running a trivial query.
    try:
        async with request.app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Check Redis
    redis_status = await redis_health()

    # Check embedding model reachability (optional, non-blocking)
    embed_status = "ok"
    try:
        import litellm

        resp = await litellm.aembedding(
            model=LLM_CONFIG["embedding_model"],
            input=["health check"],
        )
        if not resp.data:
            embed_status = "error: empty response"
    except Exception as e:
        embed_status = f"error: {str(e)}"

    all_ok = all(s == "ok" for s in [db_status, redis_status, embed_status])

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        db=db_status,
        redis=redis_status,
        version="0.2.0",
        mode=MODE,
        uptime_seconds=int(time.time() - _start_time),
    )

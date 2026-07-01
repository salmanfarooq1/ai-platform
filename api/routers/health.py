from fastapi import APIRouter, Request
from api.models.schemas import HealthResponse
from api.services.cache import redis_health

# APIRouter is FastAPI's way of grouping related routes.
# Instead of defining all routes on the app directly, we create mini-routers
# and mount them in main.py. This keeps each domain (health, ingest, search)
# in its own file — scales cleanly as the API grows.
router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    # Check DB by acquiring a connection and running a trivial query.
    # If the pool is exhausted or DB is down, this raises — we catch it.
    try:
        async with request.app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    redis_status = await redis_health()
    return HealthResponse(
        status="ok" if db_status == "ok" and redis_status == "ok" else "degraded",
        db=db_status,
        redis=redis_status,
        version="0.1.0",
    )
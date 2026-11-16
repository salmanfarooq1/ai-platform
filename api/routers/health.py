import time

from fastapi import APIRouter, Request

from api.dependencies import adapters_of
from api.models.schemas import HealthResponse
from api.services.cache import cache_health
from api.services.model_calls import embedding_provenance
from config import MODE
from core.settings import get_settings
from ports.models import ModelCatalog, ModelUse

router = APIRouter()
_start_time = time.time()

async def _check_model_metadata(catalog: ModelCatalog) -> str:
    """Read provider/model metadata only; health checks never make inference requests."""
    try:
        result = await catalog.probe()
    except Exception as exc:
        return f"error: {type(exc).__name__}"
    return "ok" if result.healthy else f"error: {result.detail}"


async def _stale_vectors(request: Request) -> int | None:
    """Chunks embedded with another model or dimension than the active one: search ignores them. None if unknown."""
    adapters = adapters_of(request)
    try:
        settings = get_settings()
        active = await adapters.model_catalog.resolve(str(settings.embed_model), use=ModelUse.EMBEDDING)
        return await adapters.knowledge.count_stale_vectors(
            embedding_provenance(active), settings.embedding_dim,
        )
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
    embed_status = await _check_model_metadata(adapters.model_catalog)
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

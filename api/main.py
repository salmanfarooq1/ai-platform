import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Request
from core.database.pool import create_pool
from config import DATABASE_CONFIG
from api.models.schemas import HealthResponse
from api.routers.health import router as health_router
from api.routers.ingest import router as ingest_router
from api.routers.search import router as search_router
from api.middleware.logging import RequestIDMiddleware, LatencyMiddleware, LoggingMiddleware
from api.middleware.finops import FinOpsMiddleware
from api.services.cache import get_redis, close_redis

# --- Lifespan ---
# FastAPI needs to know what to do when the server starts and stops.
# It's an async context manager: everything before 'yield' runs on startup,
# everything after 'yield' runs on shutdown.
# create shared resources

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    # Pool is created ONCE here, not per request.
    # app.state is FastAPI's built-in dict for storing app-level shared state.
    app.state.db_pool = await create_pool()
    app.state.redis = await get_redis()
    print(f"[startup] DB pool and Redis pool created") # replaced with logging in prod
    
    yield  # server is running, handling requests
    
    # SHUTDOWN
    # close all connections.
    await close_redis()
    await app.state.db_pool.close()
    print(f"[shutdown] DB pool and Redis pool closed")


# --- App instantiation ---

app = FastAPI(
    title="RAG Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

# MIDDLEWARE 
# FastAPI applies middleware in reverse order of addition (LIFO).
# The last one added is the first one executed.
app.add_middleware(LoggingMiddleware)
app.add_middleware(LatencyMiddleware)
app.add_middleware(FinOpsMiddleware)
app.add_middleware(RequestIDMiddleware)

# --- Root route ---
# check that the server is reachable 
# Different from /health, that actually checks dependencies.
@app.get("/")
async def root():
    return {"status": "ok", "version": "0.1.0"}

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(search_router)
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent.graph import build_agent_graph
from api.agent.router import router as agent_router
from api.mcp.transport import init_mcp_context, router as mcp_router, sse_transport
from api.middleware.finops import FinOpsMiddleware
from api.middleware.logging import LatencyMiddleware, LoggingMiddleware, RequestIDMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.token_budget import TokenBudgetMiddleware
from api.routers.analytics import router as analytics_router
from api.routers.config import router as config_router
from api.routers.docs import router as docs_router
from api.routers.feedback import router as feedback_router
from api.routers.health import router as health_router
from api.routers.ingest import router as ingest_router
from api.routers.search import router as search_router
from api.services.cache import close_redis, create_semantic_cache_index, get_redis
from core.database.pool import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    app.state.db_pool = await create_pool()
    app.state.agent_graph = build_agent_graph(app.state.db_pool)
    app.state.redis = await get_redis()
    await create_semantic_cache_index()
    init_mcp_context(app.state.db_pool)
    print("[startup] DB pool, agent graph, Redis, semantic cache, MCP context ready")

    yield

    # SHUTDOWN
    await close_redis()
    await app.state.db_pool.close()
    print("[shutdown] DB pool and Redis pool closed")


app = FastAPI(
    title="RAG Platform API",
    version="0.4.0",
    lifespan=lifespan,
)

# MIDDLEWARE — LIFO order: last added = first executed on incoming request.
# CORSMiddleware is last here so it is outermost — it runs before everything
# else, including RateLimitMiddleware. This ensures preflight (OPTIONS)
# requests get proper CORS headers even when the request would be rate-limited.
app.add_middleware(LoggingMiddleware)
app.add_middleware(LatencyMiddleware)
app.add_middleware(FinOpsMiddleware)
app.add_middleware(TokenBudgetMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:4173",  # Vite preview
        "http://localhost:3000",  # alternative dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Cost-USD", "X-Tokens-In", "X-Tokens-Out", "X-Query-ID",
        "X-Request-ID", "X-Process-Time", "X-Cache", "X-Cache-Type",
        "X-Budget-Remaining", "X-Budget-Limit",
        "X-RateLimit-Limit", "X-RateLimit-Remaining",
    ],
)


@app.get("/")
async def root():
    return {"status": "ok", "version": "0.4.0"}


app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(search_router)
app.include_router(agent_router)
app.include_router(mcp_router)
app.include_router(config_router)
app.include_router(analytics_router)
app.include_router(docs_router)
app.include_router(feedback_router)

# SseServerTransport.handle_post_message is a raw ASGI app, not a FastAPI
# endpoint function. It must be mounted directly, not registered as an
# APIRouter route. app.mount() hands the matching requests directly to the
# ASGI callable, bypassing FastAPI's request/response lifecycle entirely.
app.mount("/mcp/messages", sse_transport.handle_post_message)

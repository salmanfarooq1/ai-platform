import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Route

from api.agent.graph import build_agent_graph
from api.agent.router import router as agent_router
from api.errors import register_exception_handlers
from api.mcp.transport import handle_messages, handle_sse, init_mcp_context
from api.middleware.auth import AuthMiddleware
from api.middleware.finops import FinOpsMiddleware
from api.middleware.logging import LatencyMiddleware, LoggingMiddleware, RequestIDMiddleware
from api.observability import setup_logging, setup_tracing
from api.routers.analytics import router as analytics_router
from api.routers.config import router as config_router
from api.routers.console import router as console_router
from api.routers.docs import router as docs_router
from api.routers.feedback import router as feedback_router
from api.routers.health import router as health_router
from api.routers.ingest import router as ingest_router
from api.routers.search import router as search_router
from api.services.cache import close_redis, create_semantic_cache_index, get_redis
from api.versioning import API_PREFIX
from api.web_edge.routes import router as session_router
from core.database.pool import create_pool
from core.identity.jwt import JwtVerifier
from core.settings import get_settings
from gateway import GatewayRuntime

setup_logging()
logger = logging.getLogger("api.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    app.state.db_pool = await create_pool()
    app.state.jwt_verifier = JwtVerifier.from_settings(settings)
    app.state.agent_graph = build_agent_graph(app.state.db_pool)
    app.state.redis = await get_redis()
    app.state.gateway_runtime = GatewayRuntime(pool=app.state.db_pool, get_redis=get_redis)
    await create_semantic_cache_index()
    init_mcp_context(app.state.db_pool)
    logger.info("startup complete: DB pool, agent graph, Redis, semantic cache, MCP context ready")

    yield

    # SHUTDOWN
    await close_redis()
    await app.state.db_pool.close()
    logger.info("shutdown complete: DB pool and Redis pool closed")


def create_app() -> FastAPI:
    """Build the application. A factory so tests can get a fresh app with its own lifespan."""
    app = FastAPI(
        title="RAG Platform API",
        version="0.4.0",
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    # MIDDLEWARE — LIFO order: last added = first executed on incoming request.
    # Outermost first: CORS, RequestID, Logging, Latency, Auth, FinOps.
    # The rate limit and the daily token budget are no longer middleware: they are gateway stages
    # (`gateway/limits.py`), run by `enforce()` from the routes after Auth has verified the principal.
    # CORSMiddleware is outermost so preflight (OPTIONS) requests get CORS headers
    # even when the request would be rate-limited. RequestID is next so every
    # response (including 429s and 500s) carries X-Request-ID and X-Trace-ID and
    # every error body can quote the request id. FinOps books tokens and stamps the cost and limit headers.
    app.add_middleware(FinOpsMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(LatencyMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:4173",  # Vite preview
            "http://localhost:3000",  # alternative dev port
            *([settings.frontend_url] if settings.frontend_url else []),
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Cost-USD", "X-Tokens-In", "X-Tokens-Out", "X-Query-ID",
            "X-Request-ID", "X-Trace-ID", "X-Process-Time", "X-Cache", "X-Cache-Type",
            "X-Budget-Remaining", "X-Budget-Limit",
            "X-RateLimit-Limit", "X-RateLimit-Remaining",
        ],
    )


    @app.get("/")
    async def root():
        return {"status": "ok", "version": "0.4.0"}


    # /health stays unversioned for the platform health check. /v1/health also exists.
    app.include_router(health_router, include_in_schema=False)

    v1 = APIRouter(prefix=API_PREFIX)
    v1.include_router(health_router)
    v1.include_router(ingest_router)
    v1.include_router(search_router)
    v1.include_router(agent_router)
    v1.include_router(config_router)
    v1.include_router(analytics_router)
    v1.include_router(docs_router)
    v1.include_router(feedback_router)
    v1.include_router(session_router)
    v1.include_router(console_router)
    app.include_router(v1)

    # SseServerTransport.handle_post_message is a raw ASGI app, not a FastAPI
    # endpoint function. It must be mounted directly, not registered as an
    # APIRouter route. app.mount() hands the matching requests directly to the
    # ASGI callable, bypassing FastAPI's request/response lifecycle entirely.
    app.mount(f"{API_PREFIX}/mcp/messages", handle_messages)
    app.router.routes.append(Route(f"{API_PREFIX}/mcp/sse", endpoint=handle_sse, methods=["GET"]))

    # Last: OpenTelemetry wraps the whole app. No exporter unless OTEL_EXPORTER_OTLP_ENDPOINT is set.
    setup_tracing(app)

    return app


app = create_app()

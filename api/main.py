import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from adapters.registry import build_adapters
from api.errors import register_exception_handlers
from api.middleware.auth import AuthMiddleware
from api.middleware.finops import FinOpsMiddleware
from api.middleware.logging import LatencyMiddleware, LoggingMiddleware, RequestIDMiddleware
from api.middleware.metrics import MetricsMiddleware
from api.module_routes import mount_optional_routes
from api.observability import setup_logging, setup_tracing
from api.routers.analytics import router as analytics_router
from api.routers.config import router as config_router
from api.routers.console import router as console_router
from api.routers.docs import router as docs_router
from api.routers.feedback import router as feedback_router
from api.routers.health import router as health_router
from api.routers.ingest import router as ingest_router
from api.routers.jobs import router as jobs_router
from api.routers.receipts import router as receipts_router
from api.routers.search import router as search_router
from api.routers.system import router as system_router
from api.routers.trust import metrics_router
from api.routers.trust import router as trust_router
from api.versioning import API_PREFIX
from api.web_edge.routes import router as session_router
from config import MODEL_PRICING
from core.database.pool import create_pool
from core.identity.deploy_shape import assert_deploy_shape
from core.identity.jwt import JwtVerifier
from core.pricing import check_priced
from core.settings import get_settings
from evidence.receipts import keyring_from_settings
from gateway import GatewayRuntime
from ports import SandboxDriver

setup_logging()
logger = logging.getLogger("api.main")
settings = get_settings()


def _lifespan(
    adapter_overrides: Mapping[str, Any] | None, embedded_workers: int | None, embedded_relay: bool | None,
    sandbox_driver: SandboxDriver | None = None,
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # STARTUP
        # A hosted mode refuses to start when a model it may call has no price (an unpriced model would dodge the cost cap).
        check_priced(MODEL_PRICING, settings.mode, [settings.llm_model, settings.embed_model, *settings.embed_fallbacks])
        app.state.db_pool = await create_pool()
        await assert_deploy_shape(app.state.db_pool, settings.deploy_shape)
        app.state.jwt_verifier = JwtVerifier.from_settings(settings)
        # The composition root: one adapter per port, built from Settings (adapters/registry.py). The runtime's
        # runner reads the agent graph from app.state, because the graph itself is built from these adapters.
        runner = None
        if "agents" in settings.enabled_module_names:
            from api.agent.runner import make_agent_runner

            runner = make_agent_runner(lambda: app.state.agent_graph)
        app.state.adapters = build_adapters(settings, pool=app.state.db_pool, agent_runner=runner, overrides=adapter_overrides)
        adapters = app.state.adapters
        app.state.agent_graph = None
        if "agents" in settings.enabled_module_names:
            from api.agent.graph import build_agent_graph
            from api.mcp.transport import init_mcp_context

            app.state.agent_graph = build_agent_graph(adapters)
            init_mcp_context(app.state.db_pool, adapters, settings.enabled_module_names)
        app.state.receipt_keys = keyring_from_settings(settings)
        app.state.gateway_runtime = GatewayRuntime(pool=app.state.db_pool, cache=adapters.cache, decisions=adapters.decisions, enabled_modules=settings.enabled_module_names, events=adapters.events)
        app.state.deploy_shape = settings.deploy_shape
        await adapters.cache.ensure_semantic_index()
        # One-process hosting and tests: workers and the outbox relay inside this process (EMBEDDED_WORKERS).
        n_workers = settings.embedded_workers if embedded_workers is None else embedded_workers
        with_relay = settings.embedded_relay if embedded_relay is None else embedded_relay
        embedded = app.state.embedded = None
        if n_workers > 0 or with_relay:
            from workers.embedded import start_embedded

            embedded = start_embedded(
                settings, app.state.db_pool, adapters, app.state.gateway_runtime, app.state.agent_graph,
                workers=n_workers, relay=with_relay, keyring=app.state.receipt_keys, sandbox_driver=sandbox_driver,
            )
            app.state.embedded = embedded
        logger.info("startup complete: enabled modules %s", ",".join(sorted(settings.enabled_module_names)))

        yield

        # SHUTDOWN
        if embedded is not None:
            await embedded.stop()
        await adapters.cache.close()
        await app.state.db_pool.close()
        logger.info("shutdown complete: DB pool and cache closed")

    return lifespan


def create_app(
    adapter_overrides: Mapping[str, Any] | None = None,
    *,
    embedded_workers: int | None = None,
    embedded_relay: bool | None = None,
    sandbox_driver: SandboxDriver | None = None,
) -> FastAPI:
    """Build the application. A factory so tests can get a fresh app with its own lifespan.

    `adapter_overrides` puts other adapters behind named ports (tests pass fakes), see `adapters/registry.py`.
    `sandbox_driver` puts a fake sandbox behind the OpenShell runtime (tests). `embedded_workers` and `embedded_relay` run job workers and the outbox relay inside this process; they
    default to the EMBEDDED_WORKERS and EMBEDDED_RELAY settings (off). Ingestion and agent runs need a worker.
    """
    app = FastAPI(
        title="RAG Platform API",
        version="0.4.0",
        lifespan=_lifespan(adapter_overrides, embedded_workers, embedded_relay, sandbox_driver),
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
    app.add_middleware(MetricsMiddleware)  # outermost: counts every request, preflights and denials included


    @app.get("/")
    async def root():
        return {"status": "ok", "version": "0.4.0"}


    # /health stays unversioned for the platform health check. /v1/health also exists.
    app.include_router(health_router, include_in_schema=False)

    v1 = APIRouter(prefix=API_PREFIX)
    v1.include_router(health_router)
    v1.include_router(ingest_router)
    v1.include_router(jobs_router)
    v1.include_router(search_router)
    v1.include_router(config_router)
    v1.include_router(analytics_router)
    v1.include_router(docs_router)
    v1.include_router(feedback_router)
    v1.include_router(session_router)
    v1.include_router(console_router)
    v1.include_router(receipts_router)
    v1.include_router(trust_router)
    v1.include_router(system_router)
    app.include_router(v1)
    app.include_router(metrics_router)  # `/metrics`, unversioned like `/health`: Prometheus expects it there
    app.state.enabled_modules = settings.enabled_module_names
    app.state.deploy_shape = settings.deploy_shape
    mount_optional_routes(app, settings.enabled_module_names)

    # Last: OpenTelemetry wraps the whole app. No exporter unless OTEL_EXPORTER_OTLP_ENDPOINT is set.
    setup_tracing(app)

    return app


app = create_app()

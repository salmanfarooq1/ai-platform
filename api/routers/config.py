"""
api/routers/config.py

Exposes all platform configuration constants that the frontend needs to
stay in sync with the backend. Eliminates the need to hardcode values like
namespace names, confidence floors, or rate limits in JavaScript — a single
GET /config call at app startup is enough.

One small DB read (the caller's knowledge bases). No Redis or LLM calls.
"""
from asyncpg import Pool
from fastapi import APIRouter, Depends, Request

from api.auth import require_scope
from api.gateway_deps import entry_action, gateway_context
from config import (
    DEFAULT_DAILY_TOKEN_BUDGET,
    FEATURES,
    GUARDRAIL_CONFIG,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)
from core.database.tenant import tenant_connection
from core.identity.models import Principal, Scope
from gateway import ActionKind, EnforcementContext, require

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config(
    request: Request,
    principal: Principal = Depends(require_scope(Scope.KB_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
):
    """Return all platform constants the frontend needs to render correctly.

    Namespaces, budget limits, rate limits, guardrail thresholds, and
    agent defaults are all derived from config.py at request time —
    there is no caching, so the frontend always gets the live values.
    """
    await require(ctx, entry_action(request.url.path, ActionKind.KB_READ))
    visible = ctx.boundary.visible_kbs()  # only the knowledge bases the tenant policy allows
    pool: Pool = request.app.state.db_pool
    async with tenant_connection(pool, principal.tenant_id) as conn:
        rows = await conn.fetch("SELECT slug, description FROM knowledge_bases ORDER BY slug")
    return {
        "namespaces": {r["slug"]: r["description"] for r in rows if visible is None or r["slug"] in visible},
        "confidence_floor": GUARDRAIL_CONFIG["confidence_floor"],
        "max_query_length": GUARDRAIL_CONFIG["max_query_length"],
        "daily_token_budget": DEFAULT_DAILY_TOKEN_BUDGET,
        "rate_limit_rpm": RATE_LIMIT_REQUESTS,
        "rate_limit_window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        "reranker_enabled": FEATURES["reranker_enabled"],
        "agent_defaults": {
            "max_iterations": 6,
            "enable_verifier": True,
            "max_verify_retries": 1,
        },
    }

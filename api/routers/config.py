"""
api/routers/config.py

Exposes all platform configuration constants that the frontend needs to
stay in sync with the backend. Eliminates the need to hardcode values like
namespace names, confidence floors, or rate limits in JavaScript — a single
GET /config call at app startup is enough.

No DB, Redis, or LLM calls. Pure config echo — always fast, always cheap.
"""
from fastapi import APIRouter

from config import (
    DEFAULT_DAILY_TOKEN_BUDGET,
    FEATURES,
    GUARDRAIL_CONFIG,
    NAMESPACE_REGISTRY,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
)

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config():
    """Return all platform constants the frontend needs to render correctly.

    Namespaces, budget limits, rate limits, guardrail thresholds, and
    agent defaults are all derived from config.py at request time —
    there is no caching, so the frontend always gets the live values.
    """
    return {
        "namespaces": NAMESPACE_REGISTRY,
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

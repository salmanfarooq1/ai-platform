"""Rate limit and daily token budget, moved from the middleware without changing behaviour.

Same Redis keys (`rl:<principal id>:<window>` and `budget:<tenant id>:<UTC date>`), same limits, same
messages and error codes. One change, deliberate (Sprint 004, QA finding M2): when Redis fails, the check
raises `DependencyUnavailable` and the stage denies with 503 `dependency_unavailable`. The middleware used
to log a warning and let the request through. Booking tokens after the work is done (`record_usage`) stays
best effort: the tokens are already spent and the request cannot be denied after the fact.

`LIMITED_PATHS` and `BUDGETED_PATHS` say which entry points are metered; `api/gateway_deps.py` turns them
into the `rate` and `budget` flags of the entry action.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import config
from gateway.types import DependencyUnavailable, GatewayRuntime

logger = logging.getLogger("gateway.limits")

API_PREFIX = "/v1"
LIMITED_PATHS = tuple(f"{API_PREFIX}{p}" for p in ("/search", "/ingest", "/agent/query", "/mcp/sse"))
BUDGETED_PATHS = tuple(f"{API_PREFIX}{p}" for p in ("/search", "/agent/query"))


@dataclass(frozen=True)
class LimitResult:
    exceeded: bool
    message: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    remaining: int = 0


async def check_rate(runtime: GatewayRuntime, principal_id: UUID) -> LimitResult:
    """Fixed window per principal: Redis INCR + EXPIRE. Counts the request, whether or not it is over."""
    subject = str(principal_id)
    window = int(time.time()) // config.RATE_LIMIT_WINDOW_SECONDS
    rate_key = f"rl:{subject}:{window}"
    try:
        r = await runtime.get_redis()
        count = await r.incr(rate_key)
        if count == 1:
            await r.expire(rate_key, config.RATE_LIMIT_WINDOW_SECONDS + 1)
    except Exception as exc:
        logger.error("[rate-limit] Redis unavailable: %s", exc)
        raise DependencyUnavailable("rate limit store unavailable") from exc

    limit = config.RATE_LIMIT_REQUESTS
    remaining = max(0, limit - count)
    if count > limit:
        logger.warning("[rate-limit] principal=%s exceeded %s requests in window %s", subject, limit, window)
        retry_after = config.RATE_LIMIT_WINDOW_SECONDS - (int(time.time()) % config.RATE_LIMIT_WINDOW_SECONDS)
        return LimitResult(
            exceeded=True,
            message=(
                f"Rate limit of {limit} requests per {config.RATE_LIMIT_WINDOW_SECONDS}s exceeded "
                f"for this principal. Retry in {retry_after}s."
            ),
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"},
        )
    return LimitResult(
        exceeded=False,
        headers={"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": str(remaining)},
        remaining=remaining,
    )


def _budget_key(tenant_id: UUID) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"budget:{tenant_id}:{today}"


async def check_budget(runtime: GatewayRuntime, tenant_id: UUID) -> LimitResult:
    """Has the tenant used up today's token budget? The counter resets at UTC midnight (new key)."""
    try:
        r = await runtime.get_redis()
        current = await r.get(_budget_key(tenant_id))
        current_tokens = int(current) if current else 0
    except Exception as exc:
        logger.error("[budget] Redis unavailable for budget check: %s", exc)
        raise DependencyUnavailable("budget store unavailable") from exc

    budget = config.DEFAULT_DAILY_TOKEN_BUDGET
    if current_tokens >= budget:
        logger.warning("[budget] tenant=%s exceeded daily token budget (%s/%s)", tenant_id, current_tokens, budget)
        return LimitResult(
            exceeded=True,
            message=(
                f"Your tenant used {current_tokens} of {budget} daily tokens. "
                "The budget resets at the next UTC midnight."
            ),
            headers={"X-Budget-Remaining": "0", "X-Budget-Limit": str(budget)},
        )
    return LimitResult(exceeded=False, remaining=budget - current_tokens)


async def record_usage(runtime: GatewayRuntime, tenant_id: UUID, tokens: int) -> dict[str, str]:
    """Book `tokens` against the tenant's day. Returns the budget headers, or {} if it could not be booked."""
    if tokens <= 0:
        return {}
    key = _budget_key(tenant_id)
    try:
        r = await runtime.get_redis()
        new_total = await r.incrby(key, tokens)
        # 25 hours (not 24) so the key survives timezone edge cases.
        if new_total == tokens:
            await r.expire(key, 90000)
    except Exception as exc:
        logger.warning("[budget] Failed to record token usage: %s", exc)
        return {}
    budget = config.DEFAULT_DAILY_TOKEN_BUDGET
    return {"X-Budget-Remaining": str(max(0, budget - new_total)), "X-Budget-Limit": str(budget)}

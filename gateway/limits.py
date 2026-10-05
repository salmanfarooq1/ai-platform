"""Rate limit and daily token budget, moved from the middleware without changing behaviour.

Same cache keys (through `CachePort`) (`rl:<principal id>:<window>` and `budget:<tenant id>:<UTC date>`), same limits, same
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
        count = await runtime.cache.incr(rate_key, ttl=config.RATE_LIMIT_WINDOW_SECONDS + 1)
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


MICRO_USD = 1_000_000  # the cost counter holds whole micro-dollars, so Redis INCRBY can add them


def _cost_key(tenant_id: UUID) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:{tenant_id}:{today}"


def effective_cost_cap(policy_cap: float | None) -> float:
    """The cap in force: the tenant's own when it is lower, else the platform default. Never higher than the platform."""
    platform = config.DEFAULT_DAILY_COST_CAP_USD
    return platform if policy_cap is None else min(policy_cap, platform)


async def check_cost(runtime: GatewayRuntime, tenant_id: UUID, policy_cap: float | None) -> LimitResult:
    """Has the tenant spent its daily cost cap? The counter resets at UTC midnight (new key). Raises
    `DependencyUnavailable` when Redis cannot be read: the stage then denies (fail closed)."""
    cap = effective_cost_cap(policy_cap)
    try:
        current = await runtime.cache.get(_cost_key(tenant_id))
        spent = int(current) if current else 0
    except Exception as exc:
        logger.error("[cost] Redis unavailable for cost check: %s", exc)
        raise DependencyUnavailable("cost store unavailable") from exc
    if spent >= round(cap * MICRO_USD):
        logger.warning("[cost] tenant=%s reached its daily cost cap (%.6f of %.2f USD)", tenant_id, spent / MICRO_USD, cap)
        return LimitResult(
            exceeded=True,
            message=(
                f"Your tenant spent ${spent / MICRO_USD:.2f} of its ${cap:.2f} daily cost cap. "
                "The cap resets at the next UTC midnight."
            ),
            headers={"X-Cost-Cap-Usd": f"{cap:.2f}"},
        )
    return LimitResult(exceeded=False)


async def record_cost(runtime: GatewayRuntime, tenant_id: UUID, cost_usd: float) -> None:
    """Book the dollar cost of finished work against the tenant's day. Best effort, like `record_usage`: the work
    is done, so a Redis error is logged and not raised."""
    micro = round(cost_usd * MICRO_USD)
    if micro <= 0:
        return
    try:
        await runtime.cache.incr(_cost_key(tenant_id), micro, ttl=90000)
    except Exception as exc:
        logger.warning("[cost] Failed to record cost: %s", exc)


def _budget_key(tenant_id: UUID) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"budget:{tenant_id}:{today}"


async def check_budget(runtime: GatewayRuntime, tenant_id: UUID) -> LimitResult:
    """Has the tenant used up today's token budget? The counter resets at UTC midnight (new key)."""
    try:
        current = await runtime.cache.get(_budget_key(tenant_id))
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
        # 25 hours (not 24) so the key survives timezone edge cases.
        new_total = await runtime.cache.incr(key, tokens, ttl=90000)
    except Exception as exc:
        logger.warning("[budget] Failed to record token usage: %s", exc)
        return {}
    budget = config.DEFAULT_DAILY_TOKEN_BUDGET
    return {"X-Budget-Remaining": str(max(0, budget - new_total)), "X-Budget-Limit": str(budget)}


async def read_budget_used(runtime: GatewayRuntime, tenant_id: UUID) -> int:
    """Tokens the tenant has used today (UTC). Raises `DependencyUnavailable` when Redis cannot be read."""
    try:
        current = await runtime.cache.get(_budget_key(tenant_id))
        return int(current) if current else 0
    except Exception as exc:
        logger.error("[budget] Redis unavailable for budget read: %s", exc)
        raise DependencyUnavailable("budget store unavailable") from exc

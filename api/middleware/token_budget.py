"""
api/middleware/token_budget.py

Daily token budget enforcement per namespace using Redis.

How it works:
  - On every response that has usage data (request.state.usage),
    the middleware increments a Redis counter with the total tokens used.
  - On every incoming request, the middleware checks if the counter
    has exceeded the daily budget.
  - The counter key includes today's date (UTC), so it resets at midnight
    without needing a cron job or manual cleanup.

Position in the middleware stack (LIFO order in main.py):
  LoggingMiddleware       → innermost
  LatencyMiddleware
  FinOpsMiddleware
  TokenBudgetMiddleware   → checks budget BEFORE reaching the route
  RequestIDMiddleware
  RateLimitMiddleware     → outermost

Why between FinOps and RequestID:
  - Must run AFTER RequestID so the request_id is available for logging.
  - Must run BEFORE FinOps so that a budget-exceeded rejection is logged
    with $0.00 cost (no LLM call was made).
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.services.cache import get_redis

logger = logging.getLogger("api.budget")

# Default daily budget: 500,000 tokens per namespace.
# At Groq's llama-4-scout pricing ($0.11/M input + $0.34/M output),
# 500K tokens costs roughly $0.11. Generous for development, tight enough
# to catch runaway loops.
DEFAULT_DAILY_TOKEN_BUDGET = 500_000


class TokenBudgetMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only enforce on expensive endpoints
        if request.url.path not in ("/search", "/agent/query"):
            return await call_next(request)

        # Extract namespace (same pattern as rate limiter)
        namespace = "global"
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type:
            try:
                body = await request.body()
                if body:
                    data = json.loads(body)
                    namespace = data.get("namespace", "global")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # Build today's budget key
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        budget_key = f"budget:{namespace}:{today}"

        # Check current usage
        try:
            r = await get_redis()
            current = await r.get(budget_key)
            current_tokens = int(current) if current else 0

            if current_tokens >= DEFAULT_DAILY_TOKEN_BUDGET:
                logger.warning(
                    f"[budget] namespace={namespace} exceeded daily token budget "
                    f"({current_tokens}/{DEFAULT_DAILY_TOKEN_BUDGET})"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "daily_token_budget_exceeded",
                        "namespace": namespace,
                        "tokens_used": current_tokens,
                        "daily_limit": DEFAULT_DAILY_TOKEN_BUDGET,
                        "resets_at": f"{today}T00:00:00Z (next UTC midnight)",
                    },
                    headers={
                        "X-Budget-Remaining": "0",
                        "X-Budget-Limit": str(DEFAULT_DAILY_TOKEN_BUDGET),
                    },
                )
        except Exception as e:
            # Redis down — allow request through (same pattern as rate limiter)
            logger.warning(f"[budget] Redis unavailable for budget check: {e}")
            current_tokens = 0

        # Let the request through
        response = await call_next(request)

        # After the request, record the token usage
        usage = getattr(request.state, "usage", None)
        if usage:
            total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
            if total_tokens > 0:
                try:
                    r = await get_redis()
                    new_total = await r.incrby(budget_key, total_tokens)
                    # Set expiry to 25 hours on first write.
                    # 25 hours (not 24) ensures the key survives timezone edge cases.
                    if new_total == total_tokens:
                        await r.expire(budget_key, 90000)  # 25 hours in seconds

                    remaining = max(0, DEFAULT_DAILY_TOKEN_BUDGET - new_total)
                    response.headers["X-Budget-Remaining"] = str(remaining)
                    response.headers["X-Budget-Limit"] = str(DEFAULT_DAILY_TOKEN_BUDGET)
                except Exception as e:
                    logger.warning(f"[budget] Failed to record token usage: {e}")

        return response

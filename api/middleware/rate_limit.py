"""
api/middleware/rate_limit.py

Fixed-window rate limiting per namespace using Redis INCR + EXPIRE.

How it plugs into the middleware stack:
  RequestIDMiddleware → FinOpsMiddleware → LatencyMiddleware → LoggingMiddleware

Rate limiting runs BEFORE FinOps (outermost layer) so that rejected
requests never reach the LLM and never incur cost. The middleware order
in main.py must be:

  app.add_middleware(LoggingMiddleware)       # innermost
  app.add_middleware(LatencyMiddleware)
  app.add_middleware(FinOpsMiddleware)
  app.add_middleware(RequestIDMiddleware)
  app.add_middleware(RateLimitMiddleware)     # outermost — runs first

Remember: FastAPI applies middleware in LIFO order.
The last one added is the first one executed on an incoming request.
"""
import json
import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.services.cache import get_redis

logger = logging.getLogger("api.rate_limit")

# Configurable limits. In production these would come from config.py
# or from a per-namespace config table in the database.
RATE_LIMIT_REQUESTS = 60       # max requests per window
RATE_LIMIT_WINDOW_SECONDS = 60 # window size in seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only rate-limit the expensive endpoints. Health checks and root
        # should never be rate-limited — monitoring systems hit them constantly.
        if request.url.path not in ("/search", "/ingest", "/agent/query", "/mcp/sse"):
            return await call_next(request)

        # Extract namespace for per-tenant rate limiting.
        # Two code paths depending on content type:
        #   1. JSON body (POST /search): parse namespace from the JSON payload
        #   2. Multipart form (POST /ingest): read namespace from URL query params
        #      because parsing multipart in middleware consumes the body stream
        namespace = "global"
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            # /ingest: namespace comes as a query parameter (?namespace=legal)
            namespace = request.query_params.get("namespace", "global")
        else:
            # /search: namespace is in the JSON body
            try:
                body = await request.body()
                if body:
                    data = json.loads(body)
                    namespace = data.get("namespace", "global")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # Build the window key. Integer division groups all requests within
        # the same 60-second window under the same key.
        window = int(time.time()) // RATE_LIMIT_WINDOW_SECONDS
        rate_key = f"rl:{namespace}:{window}"

        try:
            r = await get_redis()

            # INCR is atomic in Redis. It reads, increments, and returns
            # the new value in a single operation. No race condition.
            count = await r.incr(rate_key)

            # Set expiry only on the first request in this window.
            # If count == 1, this key was just created by INCR.
            # Setting expiry on every request would be harmless but wasteful.
            if count == 1:
                await r.expire(rate_key, RATE_LIMIT_WINDOW_SECONDS + 1)
                # +1 second buffer prevents a race where the key expires
                # before the last request in the window is checked.

            remaining = max(0, RATE_LIMIT_REQUESTS - count)

            if count > RATE_LIMIT_REQUESTS:
                logger.warning(
                    f"[rate-limit] namespace={namespace} exceeded "
                    f"{RATE_LIMIT_REQUESTS} requests in window {window}"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "namespace": namespace,
                        "limit": RATE_LIMIT_REQUESTS,
                        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
                        "retry_after_seconds": RATE_LIMIT_WINDOW_SECONDS - (int(time.time()) % RATE_LIMIT_WINDOW_SECONDS),
                    },
                    headers={
                        "Retry-After": str(RATE_LIMIT_WINDOW_SECONDS - (int(time.time()) % RATE_LIMIT_WINDOW_SECONDS)),
                        "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                        "X-RateLimit-Remaining": "0",
                    },
                )

        except Exception as e:
            # Redis down? Degrade gracefully — allow the request through.
            # Rate limiting is a safety net, not a critical path.
            # Logging the failure means ops knows Redis is unhealthy.
            logger.warning(f"[rate-limit] Redis unavailable: {e}. Allowing request through.")
            remaining = RATE_LIMIT_REQUESTS  # pretend full quota

        # Request is allowed. Add rate limit headers to the response.
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

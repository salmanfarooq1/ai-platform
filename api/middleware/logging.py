"""Request context, latency and access-log middleware.

Order in main.py, outermost first:
  CORS -> RequestIDMiddleware -> LoggingMiddleware -> LatencyMiddleware -> Auth -> RateLimit -> TokenBudget -> FinOps

RequestIDMiddleware is outermost (after CORS) so every response, including rate-limit
and budget rejections, carries X-Request-ID and X-Trace-ID and every error body can
quote the request id. LoggingMiddleware turns an unhandled exception into the standard
500 error body and writes one structured access-log line per request.
"""
import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.errors import error_response
from api.observability import current_trace_id, new_request_id, request_id_var, trace_id_var

logger = logging.getLogger("api.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = new_request_id()
        trace_id = current_trace_id()
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        rid_token = request_id_var.set(request_id)
        tid_token = trace_id_var.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(rid_token)
            trace_id_var.reset(tid_token)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response


class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = (time.perf_counter() - start_time) * 1000
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Full traceback goes to the log only. The client gets the standard body.
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
            response = error_response("internal_error", "Internal server error", 500, request)
        principal = getattr(request.state, "principal", None)
        logger.info(
            "request completed",
            extra={
                "tenant_id": str(principal.tenant_id) if principal else None,
                "principal_id": str(principal.id) if principal else None,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            },
        )
        return response

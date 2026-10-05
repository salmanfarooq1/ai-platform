"""Count and time every request for `/metrics` (Sprint 008). A plain ASGI middleware, the outermost one.

The `route` label is the route template (`/v1/receipts/{decision_id}`), so one series covers every id. A request that
matches no route is labelled `unmatched`. Nothing from the request body, query or credentials is ever a label.

This FastAPI includes routers lazily, so the route object in the scope holds only its own part of the path. The template
is rebuilt from the real path: each path parameter value is put back as `{name}`.
"""
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.metrics import get_metrics

UNMATCHED = "unmatched"
# Any other method is one label, so a client cannot make the series grow by inventing methods.
KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


def method_label(scope: Scope) -> str:
    method = str(scope.get("method", "GET")).upper()
    return method if method in KNOWN_METHODS else "OTHER"


def route_label(scope: Scope) -> str:
    """The route template for a finished request, or `unmatched`."""
    path = str(scope.get("path") or "")
    if scope.get("route") is not None:
        names = {str(value): name for name, value in (scope.get("path_params") or {}).items()}
        return "/".join(f"{{{names[part]}}}" if part in names else part for part in path.split("/")) or UNMATCHED
    if scope.get("endpoint") is not None:  # a plain Route or a Mount: a fixed path
        return path or UNMATCHED
    return UNMATCHED


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            get_metrics().observe_request(route_label(scope), method_label(scope), status, time.perf_counter() - start)

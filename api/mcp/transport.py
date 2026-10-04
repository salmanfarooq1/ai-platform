"""
SSE transport bridge between the MCP server and the FastAPI app.

MCP clients connect via two HTTP endpoints:
  GET  /v1/mcp/sse     — opens a persistent Server-Sent Events stream
  POST /v1/mcp/messages/ — sends JSON-RPC requests into the active session

The GET endpoint holds the connection open for the lifetime of the
MCP session. The POST endpoint routes incoming tool calls through
the SSE transport back to the MCP server's handler.

The app_context dict (containing the DB pool) is injected into
the MCP server's dependency overrides at startup so every tool
can access shared resources without global mutable state.
"""
import logging

from mcp.server.sse import SseServerTransport
from starlette.types import Receive, Scope, Send

# Imported for their side effect: the decorators register prompts, resources and tools on the shared mcp instance.
import api.mcp.prompts  # noqa: F401 - side-effect import, registers prompts
import api.mcp.resources  # noqa: F401 - side-effect import, registers resources
import api.mcp.tools  # noqa: F401 - side-effect import, registers tools
from api.errors import decision_response, error_response
from api.mcp.context import current_principal
from api.mcp.server import mcp
from api.observability import current_request_id, current_trace_id
from api.services.cache import get_redis
from api.versioning import API_PREFIX
from core.database.tenant import DbPool
from core.identity.models import Principal
from gateway import Action, ActionKind, Decision, GatewayRuntime, build_context, enforce
from gateway.limits import LIMITED_PATHS

logger = logging.getLogger("api.mcp.transport")

sse_transport = SseServerTransport(f"{API_PREFIX}/mcp/messages/")


def init_mcp_context(pool: DbPool) -> None:
    """Inject shared app resources into MCP server context.

    Called once during FastAPI lifespan startup, after the DB pool
    is created. Tools read from this dict via
    mcp._dependency_overrides["app_context"].
    """
    mcp._dependency_overrides["app_context"] = {"pool": pool}
    logger.info("[mcp] Context initialized with DB pool")


async def _deny_response(scope: Scope, receive: Receive, send: Send, decision: Decision | None) -> None:
    """Answer a refused SSE connect with the standard error (the raw ASGI app has no exception handler)."""
    if decision is not None:
        response = decision_response(decision)
    else:
        response = error_response("unauthorized", "Missing or invalid credentials", 401, headers={"WWW-Authenticate": "Bearer"})
    await response(scope, receive, send)


class SseApp:
    """Raw ASGI app for GET /v1/mcp/sse. Opens an SSE session for an MCP client.

    The connection stays alive until the client disconnects.
    Each session gets its own read/write stream pair. The MCP
    server processes tool calls, resource reads, and prompt
    requests through these streams.

    This is a raw ASGI app, not a FastAPI endpoint function: connect_sse() writes the
    SSE response itself, and an endpoint function would then try to send a second
    response (an empty 200) when the session ends, which breaks under the middleware stack.
    It is a class instance so that Starlette routes to it as an ASGI app.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        principal = scope.get("state", {}).get("principal")
        pool = mcp._dependency_overrides.get("app_context", {}).get("pool")
        if not isinstance(principal, Principal) or pool is None:
            await _deny_response(scope, receive, send, None)  # no verified principal: never open a session
            return
        # Opening a session counts against the principal's rate limit, as it did in the middleware.
        ctx = await build_context(
            GatewayRuntime(pool, get_redis), principal, current_request_id(), current_trace_id(),
        )
        decision = await enforce(ctx, Action(ActionKind.KB_READ, rate=scope.get("path") in LIMITED_PATHS))
        if not decision.allowed:
            await _deny_response(scope, receive, send, decision)
            return
        async with sse_transport.connect_sse(scope, receive, send) as streams:
            # MCP SDK 2.x names the low-level server `_lowlevel_server` (it was `_mcp_server` in 1.x).
            await mcp._lowlevel_server.run(
                streams[0],
                streams[1],
                mcp._lowlevel_server.create_initialization_options(),
            )


class MessagesApp:
    """Raw ASGI app for POST /v1/mcp/messages/. Binds the caller's principal for the tool call.

    The SDK runs each message in the context of the request that posted it, so setting the context
    variable here, from the principal AuthMiddleware verified on this very request, makes every tool
    and resource use that caller's tenant. The SSE transport separately refuses a POST whose credential
    is not the one that opened the session (see AuthMiddleware).
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = current_principal.set(scope.get("state", {}).get("principal"))
        try:
            await sse_transport.handle_post_message(scope, receive, send)
        finally:
            current_principal.reset(token)


handle_sse = SseApp()
handle_messages = MessagesApp()

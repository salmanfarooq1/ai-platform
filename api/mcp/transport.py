"""
SSE transport bridge between the MCP server and the FastAPI app.

MCP clients connect via two HTTP endpoints:
  GET  /mcp/sse        — opens a persistent Server-Sent Events stream
  POST /mcp/messages/  — sends JSON-RPC requests into the active session

The GET endpoint holds the connection open for the lifetime of the
MCP session. The POST endpoint routes incoming tool calls through
the SSE transport back to the MCP server's handler.

The app_context dict (containing the DB pool) is injected into
the MCP server's dependency overrides at startup so every tool
can access shared resources without global mutable state.
"""
import logging

from asyncpg import Pool
from fastapi import APIRouter, Request

from api.mcp.server import mcp

# Import modules so their decorators register on the mcp instance above.
import api.mcp.tools      # noqa: F401
import api.mcp.resources  # noqa: F401
import api.mcp.prompts    # noqa: F401

from mcp.server.sse import SseServerTransport

logger = logging.getLogger("api.mcp.transport")

router = APIRouter(prefix="/mcp", tags=["mcp"])
sse_transport = SseServerTransport("/mcp/messages/")


def init_mcp_context(pool: Pool) -> None:
    """Inject shared app resources into MCP server context.

    Called once during FastAPI lifespan startup, after the DB pool
    is created. Tools read from this dict via
    mcp._dependency_overrides["app_context"].
    """
    mcp._dependency_overrides["app_context"] = {"pool": pool}
    logger.info("[mcp] Context initialized with DB pool")


@router.get("/sse")
async def handle_sse(request: Request):
    """Open an SSE session for an MCP client.

    The connection stays alive until the client disconnects.
    Each session gets its own read/write stream pair. The MCP
    server processes tool calls, resource reads, and prompt
    requests through these streams.
    """
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )

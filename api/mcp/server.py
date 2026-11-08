"""
MCP server instance.

Creates the central MCPServer object that all tools, resources, and
prompts register themselves onto. Import this module to access the
shared server instance. Do not define tools or resources here.
"""
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from gateway import REASONS, GatewayDenied


def _expected_errors(fn: Callable[..., Awaitable[Any]], error_type: type[ToolError] | type[ResourceError]):
    @wraps(fn)
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except GatewayDenied as exc:
            reason = exc.decision.reason if exc.decision.reason in REASONS else "gateway_denied"
            raise error_type(reason) from None
        except Exception:
            # Keep an unexpected exception for SDK masking, with no private cause in its logs.
            raise RuntimeError("MCP operation failed") from None
    return guarded


class PlatformMCPServer(MCPServer[Any]):
    """MCPServer plus the app-context dict that tools read (see transport.init_mcp_context)."""

    _dependency_overrides: dict[str, Any]

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        register = super().tool(*args, **kwargs)

        def decorate(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            register(_expected_errors(fn, ToolError))
            return fn
        return decorate

    def resource(self, *args: Any, **kwargs: Any) -> Any:
        register = super().resource(*args, **kwargs)

        def decorate(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            register(_expected_errors(fn, ResourceError))
            return fn
        return decorate


mcp = PlatformMCPServer(
    "RAG-Platform",
    instructions=(
        "Compliance document research server. Use search_documents for "
        "single-namespace queries and multi_namespace_search for cross-regulation "
        "comparisons. Call list_namespaces first if you are unsure which scope to use."
    ),
)
mcp._dependency_overrides = {}


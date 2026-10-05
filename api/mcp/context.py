"""The principal of the current MCP session.

`SseApp` sets it from the verified bearer credential when the SSE stream opens. Tools and resources
read it, so the tenant always comes from the credential and never from a tool argument.
"""
import json
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from api.mcp.server import mcp
from api.observability import current_request_id, current_trace_id
from core.database.tenant import DbPool
from core.identity.models import Principal, Scope
from gateway import Action, EnforcementContext, GatewayDenied, GatewayRuntime, build_context, require
from ports import Adapters

current_principal: ContextVar[Principal | None] = ContextVar("mcp_principal", default=None)


def session_pool() -> DbPool | None:
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: DbPool | None = ctx.get("pool")
    return pool


def session_adapters() -> Adapters | None:
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    adapters: Adapters | None = ctx.get("adapters")
    return adapters


def session_tenant() -> UUID | None:
    principal = current_principal.get()
    return principal.tenant_id if principal else None


def scope_denied(scope: Scope) -> str | None:
    """JSON error if the session's principal lacks `scope` (None when allowed or when there is no
    principal, which the caller reports separately). Mirrors the REST twin's scope."""
    principal = current_principal.get()
    if principal is not None and not principal.has_scope(scope):
        return json.dumps({"error": "forbidden", "reason": f"Missing required scope: {scope.value}"})
    return None


async def gate(*actions: Action) -> EnforcementContext:
    """Build the session principal's enforcement context and `require()` each action in order.

    Every tool and resource passes `tool.call(<its name>)` first, then the data and model actions it needs
    (`kb.read`, `model.invoke` for the embedding model), so allowed_tools, allowed_models and the token cap apply.

    Every MCP tool and resource goes through this before it touches data. A deny raises `GatewayDenied`,
    which the MCP server reports to the client as a tool error. The caller must check scope and principal first.
    """
    principal, pool, adapters = current_principal.get(), session_pool(), session_adapters()
    if principal is None or pool is None or adapters is None:
        raise RuntimeError("gate() needs a session principal, a pool and adapters")  # callers check them first
    ctx = await build_context(
        GatewayRuntime(pool, adapters.cache, adapters.events), principal, current_request_id(), current_trace_id())
    for action in actions:
        await require(ctx, action)
    return ctx


def blocked_query_json(denied: GatewayDenied) -> str | None:
    """The JSON error for an input-guardrail deny (the MCP contract before the gateway), else None."""
    if denied.decision.reason == "query_blocked":
        return json.dumps({"error": "query_blocked", "reason": denied.decision.message})
    return None

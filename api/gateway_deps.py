"""FastAPI glue for the gateway: the per-request context dependency and the entry-action helper."""
from fastapi import Depends, Request

from api.auth import authenticate
from api.observability import current_request_id, current_trace_id
from core.identity.models import Principal
from gateway import Action, ActionKind, EnforcementContext, GatewayRuntime, build_context
from gateway.limits import BUDGETED_PATHS, LIMITED_PATHS


def runtime_of(request: Request) -> GatewayRuntime:
    runtime: GatewayRuntime = request.app.state.gateway_runtime
    return runtime


async def gateway_context(request: Request, principal: Principal = Depends(authenticate)) -> EnforcementContext:
    """Build the enforcement context once per request. The boundary is fixed here (strict rule 3)."""
    headers: dict[str, str] = {}
    request.state.gateway_headers = headers  # FinOps puts these on the response
    request_id = str(getattr(request.state, "request_id", None) or current_request_id())
    trace_id = str(getattr(request.state, "trace_id", None) or current_trace_id())
    route = request.scope.get("route")
    required_module = getattr(route, "required_module", None)
    ctx = await build_context(runtime_of(request), principal, request_id, trace_id, headers, required_module)
    return ctx


def entry_action(
    path: str,
    kind: ActionKind,
    resource: str | None = None,
    input_text: str | None = None,
    estimated_tokens: int | None = None,
) -> Action:
    """The action for a route's own entry. Rate limit and budget apply to the paths the middleware covered."""
    return Action(
        kind=kind, resource=resource, input_text=input_text, estimated_tokens=estimated_tokens,
        rate=path in LIMITED_PATHS, budget=path in BUDGETED_PATHS,
    )

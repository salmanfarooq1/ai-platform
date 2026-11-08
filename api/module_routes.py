"""Mount trusted optional routes, or credential-preserving recorded deny handlers."""
from dataclasses import dataclass
from importlib import import_module
from typing import NoReturn

from fastapi import Depends, FastAPI, Request
from starlette.routing import Route

from api.auth import require_any_scope, require_scope
from api.gateway_deps import entry_action, gateway_context
from api.run_authority import run_ctx
from api.versioning import API_PREFIX
from core.identity.models import Principal, Scope
from core.modules import MODULE_BY_NAME
from gateway import Action, ActionKind, EnforcementContext, require


@dataclass(frozen=True)
class DisabledRoute:
    path: str
    methods: tuple[str, ...]
    kind: ActionKind
    scopes: tuple[Scope, ...] = ()
    run_bound: bool = False
    run_read: bool = False


# Closed registration data: never populated from request fields or model output.
DISABLED_AGENT_ROUTES = (
    DisabledRoute("/agent/query", ("POST",), ActionKind.AGENT_RUN, (Scope.AGENT,)),
    DisabledRoute("/agent/runs", ("GET",), ActionKind.KB_READ, (Scope.AGENT, Scope.AUDIT_READ), run_read=True),
    DisabledRoute("/agent/runs/{execution_id}", ("GET",), ActionKind.KB_READ,
                  (Scope.AGENT, Scope.AUDIT_READ), run_read=True),
    DisabledRoute("/sandbox/runs/{execution_id}/tools/{name}", ("POST",), ActionKind.TOOL_CALL, run_bound=True),
    DisabledRoute("/sandbox/runs/{execution_id}/model", ("POST",), ActionKind.MODEL_INVOKE, run_bound=True),
    DisabledRoute("/mcp/sse", ("GET", "HEAD"), ActionKind.KB_READ, (Scope.QUERY, Scope.KB_READ)),
    DisabledRoute("/mcp/messages", ("POST",), ActionKind.KB_READ, (Scope.QUERY, Scope.KB_READ)),
    DisabledRoute("/mcp/messages/", ("POST",), ActionKind.KB_READ, (Scope.QUERY, Scope.KB_READ)),
    DisabledRoute("/mcp/messages/{path:path}", ("POST",), ActionKind.KB_READ, (Scope.QUERY, Scope.KB_READ)),
)


def _disabled_endpoint(spec: DisabledRoute):
    if spec.run_bound:
        async def sandbox_disabled(request: Request, ctx: EnforcementContext = Depends(run_ctx)) -> NoReturn:
            resource = request.path_params.get("name")
            await require(ctx, Action(spec.kind, resource=resource))
            raise RuntimeError("disabled route registry disagrees with gateway module settings")

        return sandbox_disabled

    permission = require_scope(spec.scopes[0]) if len(spec.scopes) == 1 else require_any_scope(*spec.scopes)

    async def disabled(
        request: Request, principal: Principal = Depends(permission),
        ctx: EnforcementContext = Depends(gateway_context),
    ) -> NoReturn:
        if spec.run_read and principal.has_scope(Scope.AUDIT_READ):
            action = Action(ActionKind.AUDIT_READ, resource="runs")
        else:
            action = entry_action(request.url.path, spec.kind)
        await require(ctx, action)
        raise RuntimeError("disabled route registry disagrees with gateway module settings")

    return disabled


def mount_optional_routes(app: FastAPI, enabled_modules: frozenset[str]) -> None:
    """Call after foundation routers are included; final route objects retain attribution."""
    app.state.enabled_modules = enabled_modules
    app.state.mcp_mounted = False
    start = len(app.router.routes)
    if "agents" in enabled_modules:
        for target in MODULE_BY_NAME["agents"].routers:
            module, attribute = target.split(":", 1)
            router = getattr(import_module(module), attribute)
            # FastAPI versions that delegate to an included router expose its
            # source APIRoute in request.scope. Older versions clone it instead.
            for route in router.routes:
                setattr(route, "required_module", "agents")
            app.include_router(router, prefix=API_PREFIX)
        # This raw transport has no FastAPI router and is loaded only in M3.
        for target in MODULE_BY_NAME["agents"].transports:
            transport = import_module(target)
            app.mount(f"{API_PREFIX}/mcp/messages", transport.handle_messages)
            app.router.routes.append(Route(f"{API_PREFIX}/mcp/sse", endpoint=transport.handle_sse, methods=["GET"]))
            app.state.mcp_mounted = True
    else:
        for index, spec in enumerate(DISABLED_AGENT_ROUTES):
            app.add_api_route(
                API_PREFIX + spec.path, _disabled_endpoint(spec), methods=list(spec.methods),
                name=f"agents_disabled_{index}", include_in_schema=False, response_model=None,
            )
    # Also tag final route objects for FastAPI versions that clone on inclusion.
    for route in app.router.routes[start:]:
        setattr(route, "required_module", "agents")

"""Authentication and coarse authorization.

`AuthMiddleware` (api/middleware/auth.py) verifies the bearer credential and puts the `Principal` on
`request.state.principal`, before the rate limiter and token budget run. The dependencies here are
what routes declare: `authenticate` returns that principal and `require_scope(scope)` checks one
scope. The tenant is only ever read from the principal (strict rule 1), never from the request.
"""
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.identity.models import Principal, Scope
from ports import KnowledgeStore

# Declares the bearer scheme in the OpenAPI document. The credential itself is verified by AuthMiddleware.
_bearer_scheme = HTTPBearer(auto_error=False, description="API key (gap_<prefix>_<secret>) or JWT")

UNAUTHORIZED_MESSAGE = "Missing or invalid credentials"


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail=UNAUTHORIZED_MESSAGE, headers={"WWW-Authenticate": "Bearer"})


async def authenticate(request: Request) -> Principal:
    """The verified principal of this request. 401 if the middleware did not authenticate one."""
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise unauthorized()
    return principal


async def record_scope_denial(request: Request, principal: Principal, scope: Scope) -> None:
    """Send a missing-scope refusal through `enforce()` so it leaves a decision row (stage `boundary`,
    reason `missing_scope`). The caller still answers the same 403 body; a failure here never changes it."""
    try:
        from gateway import Action, ActionKind, build_context, enforce
        from gateway.enforce import Stage
        from gateway.types import Decision

        async def missing_scope(ctx, action):
            return Decision(allowed=False, stage="boundary", reason="missing_scope", policy_version=ctx.boundary.policy_version)

        stage: Stage = missing_scope
        kind = {
            Scope.KB_READ: ActionKind.KB_READ, Scope.KB_WRITE: ActionKind.KB_WRITE, Scope.QUERY: ActionKind.KB_READ,
            Scope.AGENT: ActionKind.AGENT_RUN, Scope.AUDIT_READ: ActionKind.AUDIT_READ, Scope.ADMIN: ActionKind.AGENT_RUN,
        }[scope]
        ctx = await build_context(
            request.app.state.gateway_runtime, principal,
            str(getattr(request.state, "request_id", "-")), str(getattr(request.state, "trace_id", "-")),
        )
        await enforce(ctx, Action(kind), [("boundary", stage)])
    except Exception:
        logging.getLogger("api.auth").error("scope denial not recorded", exc_info=True)


async def record_run_token_denial(request: Request, grant: Any) -> None:
    """A run token was used on a route outside its run: leave a decision row (stage `boundary`, reason
    `run_token_scope`) under the run's `execution_id`. The caller still answers 403; a failure here changes nothing."""
    try:
        # At most one deny row per token and path per minute (Sprint 009 QA L1): a leaked token cannot fill the table. The
        # use is still refused. If the counter cannot be read, no row is written.
        import hashlib

        key = f"rtd:{grant.token_id}:{hashlib.sha256(request.url.path.encode()).hexdigest()[:16]}"
        if await request.app.state.gateway_runtime.cache.incr(key, ttl=60) > 1:
            return
        from gateway import Action, ActionKind, enforce
        from gateway.boundary import ExecutionBoundary
        from gateway.enforce import Stage
        from gateway.types import Decision, EnforcementContext

        async def outside_run(ctx, action):
            return Decision(allowed=False, stage="boundary", reason="run_token_scope", policy_version=ctx.boundary.policy_version)

        stage: Stage = outside_run
        ctx = EnforcementContext(
            principal=grant.principal, request_id=str(getattr(request.state, "request_id", "-")),
            trace_id=str(getattr(request.state, "trace_id", "-")), boundary=ExecutionBoundary.from_payload(grant.boundary),
            runtime=request.app.state.gateway_runtime, execution_id=grant.execution_id,
        )
        await enforce(ctx, Action(ActionKind.TOOL_CALL), [("boundary", stage)])
    except Exception:
        logging.getLogger("api.auth").error("run token denial not recorded", exc_info=True)


def require_scope(scope: Scope) -> Callable[[Request], Awaitable[Principal]]:
    """Route dependency: an authenticated principal that holds `scope` (`admin` holds every scope)."""

    async def dependency(
        request: Request,
        _credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> Principal:
        principal = await authenticate(request)
        if not principal.has_scope(scope):
            await record_scope_denial(request, principal, scope)
            raise HTTPException(status_code=403, detail=f"Missing required scope: {scope.value}")
        return principal

    dependency.__name__ = f"require_{scope.value.replace(':', '_')}"
    return dependency


def require_any_scope(*scopes: Scope) -> Callable[[Request], Awaitable[Principal]]:
    """Route dependency: an authenticated principal that holds at least one of `scopes` (`admin` holds all). A
    refusal is recorded as a missing-scope decision for the first scope listed."""

    async def dependency(
        request: Request,
        _credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> Principal:
        principal = await authenticate(request)
        if not any(principal.has_scope(scope) for scope in scopes):
            await record_scope_denial(request, principal, scopes[0])
            raise HTTPException(status_code=403, detail=f"Missing required scope: {' or '.join(s.value for s in scopes)}")
        return principal

    dependency.__name__ = "require_any_" + "_".join(s.value.replace(":", "_") for s in scopes)
    return dependency


async def require_kb(store: KnowledgeStore, principal: Principal, slug: str) -> None:
    """404 `kb_not_found` unless `slug` is one of the caller's own knowledge bases.

    A foreign KB and a missing KB give the identical response (no existence leak). Row-level security
    already hides other tenants' rows, so the lookup needs no extra tenant filter.
    """
    if not await store.kb_exists(principal.tenant_id, slug):
        raise kb_not_found()


KB_NOT_FOUND_MESSAGE = "Knowledge base not found"


def kb_not_found() -> HTTPException:
    # One constant body for a foreign KB and a missing one, so the response does not reveal which it was.
    return HTTPException(status_code=404, detail={"error": "kb_not_found", "reason": KB_NOT_FOUND_MESSAGE})

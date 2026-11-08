"""Authenticate every `/v1` request except the public ones, before the rate limiter and budget run.

A bearer key, run token (`grt_`, one sandboxed run, see `core/identity/run_tokens.py`) or JWT is tried first. With no bearer, the `gap_session` cookie of the web edge (api/web_edge/) is
resolved to the same Principal, and an unsafe method then needs a matching `X-CSRF-Token` (403 `csrf_failed`).

Order in main.py, outermost first: CORS, RequestID, Logging, Latency, Auth, RateLimit, TokenBudget, FinOps.
A missing, malformed, unknown, revoked or expired credential is answered 401 with one generic message
(the reason is logged, never the token). If verification itself fails (database down) the request is
denied with 503 (strict rule 3: fail closed). Scope checks for routes live in `api.auth.require_scope`;
the MCP endpoints are raw ASGI apps: the session needs `query` or `kb:read` here, and each tool checks its own scope.
"""
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.auth import record_run_token_denial
from api.errors import error_response
from api.versioning import API_PREFIX
from api.web_edge.auth import principal_from_session
from api.web_edge.session import COOKIE_NAME, CSRF_HEADER, SAFE_METHODS, WebSession, csrf_matches
from core.identity.jwt import JwtError, JwtVerifier
from core.identity.keys import KEY_PREFIX_TAG
from core.identity.models import Principal, Scope
from core.identity.run_tokens import RunGrant, authenticate_run_token, is_run_token
from core.identity.store import authenticate_api_key, confirm_jwt_principal
from core.settings import get_settings

logger = logging.getLogger("api.auth")

PUBLIC_PATHS = frozenset({"/", "/health", f"{API_PREFIX}/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})
_MCP_PREFIX = f"{API_PREFIX}/mcp/"
# The two routes that create a session. They run before any credential exists, so they are public (POST only).
SESSION_CREATE_PATHS = frozenset({f"{API_PREFIX}/session", f"{API_PREFIX}/session/preview"})


def requires_auth(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return False
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # `/metrics` is outside `/v1`. It is public only when METRICS_PUBLIC is true; otherwise the route needs `admin`.
        guarded_metrics = path == "/metrics" and not get_settings().metrics_public
        if request.method == "OPTIONS" or not (requires_auth(path) or guarded_metrics):
            return await call_next(request)
        if request.method == "POST" and path in SESSION_CREATE_PATHS:
            return await call_next(request)

        def deny(reason: str):
            logger.info("authentication failed: %s", reason, extra={"path": path})
            return error_response(
                "unauthorized", "Missing or invalid credentials", 401, request,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = _bearer_token(request)
        cookie = request.cookies.get(COOKIE_NAME)
        if token is None and not cookie:
            return deny("no bearer token and no session cookie")

        principal: Principal | None
        web_session: WebSession | None = None
        run_grant: RunGrant | None = None
        try:
            if token is None:
                # Order: bearer first, then the web session cookie. A bad bearer is never rescued by a cookie.
                resolved = await principal_from_session(request, cookie or "")
                if resolved is None:
                    return deny("session rejected")
                principal, web_session = resolved
                if request.method not in SAFE_METHODS and not csrf_matches(web_session, request.headers.get(CSRF_HEADER)):
                    logger.info("csrf check failed", extra={"path": path})
                    return error_response("csrf_failed", "Missing or invalid CSRF token", 403, request)
            elif token.startswith(f"{KEY_PREFIX_TAG}_"):
                principal = await authenticate_api_key(request.app.state.db_pool, token)
                if principal is None:
                    return deny("api key rejected")
            elif is_run_token(token):
                # A run token (Sprint 009) is the credential of one sandboxed run. It opens only that run's routes.
                run_grant = await authenticate_run_token(request.app.state.db_pool, token)
                if run_grant is None:
                    return deny("run token rejected")
                if not run_grant.covers(path):
                    logger.info("run token used outside its run", extra={"path": path})
                    await record_run_token_denial(request, run_grant)
                    return error_response("forbidden", "This run token does not open this route", 403, request)
                principal = run_grant.principal
            else:
                verifier: JwtVerifier | None = getattr(request.app.state, "jwt_verifier", None)
                if verifier is None:
                    return deny("not an api key and JWT is not configured")
                try:
                    claimed = await verifier.verify(token)
                except JwtError as exc:
                    return deny(f"jwt rejected: {exc}")
                principal = await confirm_jwt_principal(request.app.state.db_pool, claimed)
                if principal is None:
                    return deny("jwt principal unknown, disabled, or not in the token's tenant")
        except Exception:
            logger.error("authentication unavailable", exc_info=True)
            return error_response("service_unavailable", "Authentication is unavailable", 503, request)

        # MCP: a session needs at least one scope that some tool accepts. Each tool and resource then checks
        # the scope of its REST twin (search: query; ingestion status, cost summary, resources: kb:read).
        if path.startswith(_MCP_PREFIX) and not (principal.has_scope(Scope.QUERY) or principal.has_scope(Scope.KB_READ)):
            return error_response("forbidden", "Missing required scope: query or kb:read", 403, request)

        request.state.principal = principal
        request.state.web_session = web_session
        request.state.run_grant = run_grant
        if path.startswith(_MCP_PREFIX):
            # The MCP SSE transport binds a session to the credential that opened it and answers 404 to
            # any other caller of that session. It reads `scope["user"]` for that. The token itself is
            # deliberately not carried over: the principal and tenant ids identify the credential.
            runtime = getattr(request.app.state, "gateway_runtime", None)
            if runtime is not None and "agents" in runtime.enabled_modules and getattr(request.app.state, "mcp_mounted", False):
                from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
                from mcp.server.auth.provider import AccessToken

                request.scope["user"] = AuthenticatedUser(AccessToken(
                    token="", client_id=str(principal.id), subject=str(principal.tenant_id), scopes=sorted(principal.scopes),
                ))
        return await call_next(request)

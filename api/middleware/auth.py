"""Authenticate every `/v1` request except the public ones, before the rate limiter and budget run.

Order in main.py, outermost first: CORS, RequestID, Logging, Latency, Auth, RateLimit, TokenBudget, FinOps.
A missing, malformed, unknown, revoked or expired credential is answered 401 with one generic message
(the reason is logged, never the token). If verification itself fails (database down) the request is
denied with 503 (strict rule 3: fail closed). Scope checks for routes live in `api.auth.require_scope`;
the MCP endpoints are raw ASGI apps: the session needs `query` or `kb:read` here, and each tool checks its own scope.
"""
import logging

from fastapi import Request
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.middleware.base import BaseHTTPMiddleware

from api.errors import error_response
from api.versioning import API_PREFIX
from core.identity.jwt import JwtError, JwtVerifier
from core.identity.keys import KEY_PREFIX_TAG
from core.identity.models import Principal, Scope
from core.identity.store import authenticate_api_key, confirm_jwt_principal

logger = logging.getLogger("api.auth")

PUBLIC_PATHS = frozenset({"/", "/health", f"{API_PREFIX}/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})
_MCP_PREFIX = f"{API_PREFIX}/mcp/"


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
        if request.method == "OPTIONS" or not requires_auth(path):
            return await call_next(request)

        def deny(reason: str):
            logger.info("authentication failed: %s", reason, extra={"path": path})
            return error_response(
                "unauthorized", "Missing or invalid credentials", 401, request,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = _bearer_token(request)
        if token is None:
            return deny("no bearer token")

        principal: Principal | None
        try:
            if token.startswith(f"{KEY_PREFIX_TAG}_"):
                principal = await authenticate_api_key(request.app.state.db_pool, token)
                if principal is None:
                    return deny("api key rejected")
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
        if path.startswith(_MCP_PREFIX):
            # The MCP SSE transport binds a session to the credential that opened it and answers 404 to
            # any other caller of that session. It reads `scope["user"]` for that. The token itself is
            # deliberately not carried over: the principal and tenant ids identify the credential.
            request.scope["user"] = AuthenticatedUser(AccessToken(
                token="", client_id=str(principal.id), subject=str(principal.tenant_id), scopes=sorted(principal.scopes),
            ))
        return await call_next(request)

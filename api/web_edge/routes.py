"""Session routes: sign in with an API key, read the session, sign out, start a read-only preview.

`POST /v1/session` and `POST /v1/session/preview` are public (no credential yet); `AuthMiddleware` lets exactly
those two through. `GET` and `DELETE /v1/session` need the cookie, and `DELETE` needs the CSRF header
whenever a session cookie is sent, even with a bearer header.
"""
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from api.dependencies import adapters_of
from api.errors import error_response
from api.web_edge.session import (
    COOKIE_NAME,
    CSRF_HEADER,
    PREVIEW_REMOVED_SCOPES,
    SLIDING_TTL,
    WebSession,
    create_session,
    csrf_matches,
    delete_session,
    load_session,
)
from core.database.tenant import DbPool, tenant_connection
from core.identity.keys import parse_key
from core.identity.models import Principal
from core.identity.store import authenticate_api_key
from core.settings import Settings, get_settings

logger = logging.getLogger("api.web_edge")

router = APIRouter(prefix="/session", tags=["session"])

SIGN_IN_LIMIT = 10
SIGN_IN_WINDOW_SECONDS = 60
INVALID_CREDENTIALS = "Invalid credentials"


class SignInRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


class PrincipalInfo(BaseModel):
    id: UUID
    name: str
    kind: str


class TenantInfo(BaseModel):
    id: UUID
    slug: str


class SessionInfo(BaseModel):
    principal: PrincipalInfo
    tenant: TenantInfo
    scopes: list[str]
    csrf_token: str
    preview: bool
    expires_at: datetime


def edge_settings() -> Settings:
    """The settings the web edge reads (mode and preview principal). A dependency so tests can replace it."""
    return get_settings()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _sign_in_allowed(request: Request) -> tuple[bool, int]:
    """Fixed window per client IP in Redis. Raises when Redis fails (the caller answers 503)."""
    window = int(time.time()) // SIGN_IN_WINDOW_SECONDS
    key = f"rl:ip:signin:{_client_ip(request)}:{window}"
    count = await adapters_of(request).cache.incr(key, ttl=SIGN_IN_WINDOW_SECONDS + 1)
    retry_after = SIGN_IN_WINDOW_SECONDS - (int(time.time()) % SIGN_IN_WINDOW_SECONDS)
    return count <= SIGN_IN_LIMIT, retry_after


def _set_cookie(response: Response, session_id: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME, session_id, max_age=int(SLIDING_TTL.total_seconds()), path="/",
        httponly=True, samesite="strict", secure=settings.mode != "local",
    )


async def _info(pool: DbPool, session: WebSession, principal_kind: str) -> SessionInfo:
    async with tenant_connection(pool, session.tenant_id) as conn:
        who = await conn.fetchrow("SELECT name FROM principals WHERE id = $1", session.principal_id)
        tenant = await conn.fetchrow("SELECT slug FROM tenants WHERE id = $1", session.tenant_id)
    if who is None or tenant is None:
        raise LookupError("session principal or tenant is gone")
    return SessionInfo(
        principal=PrincipalInfo(id=session.principal_id, name=who["name"], kind=principal_kind),
        tenant=TenantInfo(id=session.tenant_id, slug=tenant["slug"]),
        scopes=sorted(session.scopes),
        csrf_token=session.csrf,
        preview=session.preview,
        expires_at=session.expires_at(datetime.now(timezone.utc)),
    )


@router.post("", response_model=SessionInfo, responses={401: {"description": "invalid_credentials"}, 429: {"description": "rate limited"}})
async def sign_in(
    body: SignInRequest, request: Request, response: Response, settings: Settings = Depends(edge_settings),
):
    """Exchange an API key for a browser session. The key is checked once and never stored."""
    try:
        allowed, retry_after = await _sign_in_allowed(request)
    except Exception:
        logger.error("sign-in rate limit store unavailable", exc_info=True)
        return error_response("service_unavailable", "A required service is unavailable. Try again shortly.", 503, request)
    if not allowed:
        return error_response(
            "rate_limit_exceeded", f"Too many sign-in attempts. Retry in {retry_after}s.", 429, request,
            headers={"Retry-After": str(retry_after)},
        )
    pool: DbPool = request.app.state.db_pool
    try:
        principal = await authenticate_api_key(pool, body.api_key)
    except Exception:
        logger.error("sign-in unavailable", exc_info=True)
        return error_response("service_unavailable", "Authentication is unavailable", 503, request)
    if principal is None:
        logger.info("sign-in failed")
        return error_response("invalid_credentials", INVALID_CREDENTIALS, 401, request)
    parsed = parse_key(body.api_key)
    prefix = parsed[0] if parsed else None
    return await _start(request, response, principal, principal.scopes, preview=False, settings=settings, key_prefix=prefix)


@router.post("/preview", response_model=SessionInfo, responses={404: {"description": "preview is not available"}})
async def start_preview(request: Request, response: Response, settings: Settings = Depends(edge_settings)):
    """An automatic read-only session for the configured preview principal. 404 unless the mode allows it."""
    unavailable = error_response("not_found", "Not found", 404, request)
    if settings.mode != "public-preview" or settings.preview_principal_id is None:
        return unavailable
    pool: DbPool = request.app.state.db_pool
    try:
        row = await pool.fetchrow("SELECT * FROM auth_lookup_preview($1)", settings.preview_principal_id)
    except Exception:
        logger.error("preview principal lookup failed", exc_info=True)
        return error_response("service_unavailable", "Authentication is unavailable", 503, request)
    if row is None or row["principal_disabled_at"] is not None:
        logger.warning("preview principal is missing or disabled")
        return unavailable
    scopes = frozenset(row["scopes"]) - PREVIEW_REMOVED_SCOPES
    if not scopes:
        logger.warning("preview principal has no scope left after removing kb:write and admin")
        return unavailable
    principal = Principal(id=row["principal_id"], tenant_id=row["tenant_id"], kind=row["principal_kind"], scopes=scopes)
    return await _start(request, response, principal, scopes, preview=True, settings=settings)


async def _start(request: Request, response: Response, principal: Principal, scopes: frozenset[str], preview: bool, settings: Settings, key_prefix: str | None = None):
    try:
        session_id, session = await create_session(adapters_of(request).cache, principal.id, principal.tenant_id, scopes, preview, key_prefix)
    except Exception:
        logger.error("session store unavailable", exc_info=True)
        return error_response("service_unavailable", "A required service is unavailable. Try again shortly.", 503, request)
    try:
        info = await _info(request.app.state.db_pool, session, principal.kind)
    except Exception:
        logger.error("could not build the session info, dropping the new session", exc_info=True)
        try:
            await delete_session(adapters_of(request).cache, session_id)
        except Exception:
            logger.error("could not delete the new session", exc_info=True)
        return error_response("service_unavailable", "A required service is unavailable. Try again shortly.", 503, request)
    _set_cookie(response, session_id, settings)
    return info


@router.get("", response_model=SessionInfo, responses={401: {"description": "no session"}})
async def read_session(request: Request):
    """The current cookie session. A bearer-only caller has no session and gets 401."""
    principal = getattr(request.state, "principal", None)
    session: WebSession | None = getattr(request.state, "web_session", None)
    if not isinstance(principal, Principal) or session is None:
        return error_response("unauthorized", "Missing or invalid credentials", 401, request)
    return await _info(request.app.state.db_pool, session, principal.kind)


@router.delete("", status_code=204, responses={403: {"description": "csrf_failed"}})
async def sign_out(request: Request, settings: Settings = Depends(edge_settings)):
    """Delete the session and clear the cookie. The CSRF header is checked by the auth middleware."""
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        try:
            # With a bearer header the middleware skips CSRF, but a cookie here is still a session to protect.
            live = await load_session(adapters_of(request).cache, cookie)
            if live is not None and not csrf_matches(live, request.headers.get(CSRF_HEADER)):
                return error_response("csrf_failed", "Missing or invalid CSRF token", 403, request)
            await delete_session(adapters_of(request).cache, cookie)
        except Exception:
            logger.error("session store unavailable on sign-out", exc_info=True)
            return error_response("service_unavailable", "A required service is unavailable. Try again shortly.", 503, request)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=settings.mode != "local")
    return response

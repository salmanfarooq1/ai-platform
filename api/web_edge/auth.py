"""Resolve a `gap_session` cookie to the `Principal` a key would give. Used by `AuthMiddleware`, after bearer."""
import logging
from typing import Any, cast

from fastapi import Request

from api.dependencies import adapters_of
from api.web_edge.session import PREVIEW_REMOVED_SCOPES, WebSession, delete_session, load_session
from core.identity.models import Principal, PrincipalKind

logger = logging.getLogger("api.web_edge")


async def principal_from_session(request: Request, cookie: str) -> tuple[Principal, WebSession] | None:
    """The principal and session for a cookie, or None (unknown, expired, or its principal is disabled or gone).

    The principal row is checked on every request, so disabling a principal ends its sessions at once. The key
    the session was opened with is checked too: once it is revoked the session is deleted. A preview session
    needs the principal to still have an unrevoked key. The scopes come from the session (a scope change needs
    a new sign-in). Raises on a Redis or database error: the middleware answers 503.
    """
    cache = adapters_of(request).cache
    session = await load_session(cache, cookie)
    if session is None:
        return None
    row = await request.app.state.db_pool.fetchrow(
        "SELECT * FROM auth_lookup_principal($1, $2)", session.principal_id, session.tenant_id,
    )
    if row is None or row["tenant_id"] != session.tenant_id or row["principal_disabled_at"] is not None:
        logger.info("session principal is gone or disabled")
        return None
    if not await _key_is_live(request, session, row["principal_id"]):
        logger.info("session key is revoked or gone")
        await delete_session(cache, cookie)
        return None
    principal = Principal(
        id=row["principal_id"], tenant_id=row["tenant_id"],
        kind=cast(PrincipalKind, row["principal_kind"]), scopes=session.scopes,
    )
    return principal, session


async def _key_is_live(request: Request, session: WebSession, principal_id: Any) -> bool:
    pool = request.app.state.db_pool
    if session.preview:
        row = await pool.fetchrow("SELECT * FROM auth_lookup_preview($1)", session.principal_id)
        return row is not None and bool(frozenset(row["scopes"]) - PREVIEW_REMOVED_SCOPES)
    if session.key_prefix is None:
        return False  # a session without a key reference is not one this code made: fail closed
    row = await pool.fetchrow("SELECT * FROM auth_lookup_key($1)", session.key_prefix)
    return row is not None and row["revoked_at"] is None and row["principal_id"] == principal_id

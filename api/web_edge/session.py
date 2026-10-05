"""The session store: Redis keys `websess:<sha256(session id)>` holding JSON.

The value is `{principal_id, tenant_id, scopes, csrf, created_at, preview, key_prefix}`. `key_prefix` is the public
identifier of the key used to sign in (null for preview), checked against revocation on every request. It never
holds an API key secret or any key material. The id is 32 random bytes (urlsafe) and only its SHA-256 is a Redis key, so a Redis dump does not
yield a usable cookie. The TTL is 8 hours and slides on use, with an absolute cap of 24 hours from creation.
"""
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from ports import CachePort

COOKIE_NAME = "gap_session"
CSRF_HEADER = "X-CSRF-Token"
KEY_PREFIX = "websess:"
SLIDING_TTL = timedelta(hours=8)
ABSOLUTE_CAP = timedelta(hours=24)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Preview sessions never hold these, whatever the preview principal's keys grant.
PREVIEW_REMOVED_SCOPES = frozenset({"kb:write", "admin"})


@dataclass(frozen=True)
class WebSession:
    principal_id: UUID
    tenant_id: UUID
    scopes: frozenset[str]
    csrf: str
    created_at: datetime
    preview: bool
    key_prefix: str | None = None

    @property
    def absolute_expiry(self) -> datetime:
        return self.created_at + ABSOLUTE_CAP

    def expires_at(self, now: datetime) -> datetime:
        return min(now + SLIDING_TTL, self.absolute_expiry)


def redis_key(session_id: str) -> str:
    return KEY_PREFIX + hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _encode(session: WebSession) -> str:
    return json.dumps({
        "principal_id": str(session.principal_id),
        "tenant_id": str(session.tenant_id),
        "scopes": sorted(session.scopes),
        "csrf": session.csrf,
        "created_at": session.created_at.isoformat(),
        "preview": session.preview,
        "key_prefix": session.key_prefix,
    })


def _decode(raw: Any) -> WebSession | None:
    try:
        data = json.loads(raw)
        return WebSession(
            principal_id=UUID(data["principal_id"]),
            tenant_id=UUID(data["tenant_id"]),
            scopes=frozenset(str(s) for s in data["scopes"]),
            csrf=str(data["csrf"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            preview=bool(data["preview"]),
            key_prefix=data.get("key_prefix") if isinstance(data.get("key_prefix"), str) else None,
        )
    except (ValueError, KeyError, TypeError):
        return None


def _seconds(delta: timedelta) -> int:
    return max(1, int(delta.total_seconds()))


async def create_session(cache: CachePort, principal_id: UUID, tenant_id: UUID, scopes: frozenset[str], preview: bool, key_prefix: str | None = None) -> tuple[str, WebSession]:
    """Store a new session. Returns the cookie value (the only time it exists in the clear) and the session."""
    session = WebSession(
        principal_id=principal_id, tenant_id=tenant_id, scopes=scopes,
        csrf=secrets.token_urlsafe(32), created_at=datetime.now(timezone.utc), preview=preview,
        key_prefix=key_prefix,
    )
    session_id = secrets.token_urlsafe(32)
    await cache.set(redis_key(session_id), _encode(session), ttl=_seconds(SLIDING_TTL))
    return session_id, session


async def load_session(cache: CachePort, session_id: str) -> WebSession | None:
    """The live session for a cookie value, or None. A hit slides the TTL, never past the 24 hour cap.

    Raises `CacheUnavailable` on a cache error: the caller answers 503 (fail closed).
    """
    key = redis_key(session_id)
    raw = await cache.get(key)
    if raw is None:
        return None
    session = _decode(raw)
    now = datetime.now(timezone.utc)
    if session is None or now >= session.absolute_expiry:
        await cache.delete(key)
        return None
    await cache.expire(key, _seconds(min(SLIDING_TTL, session.absolute_expiry - now)))
    return session


async def delete_session(cache: CachePort, session_id: str) -> None:
    await cache.delete(redis_key(session_id))


def csrf_matches(session: WebSession, supplied: str | None) -> bool:
    return bool(supplied) and hmac.compare_digest(session.csrf.encode("utf-8"), str(supplied).encode("utf-8"))

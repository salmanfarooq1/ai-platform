"""Run tokens: the short-lived credential a sandboxed agent uses to call the gateway (Sprint 009, ADR-0009).

A run token is bound to one `execution_id` and one principal, and carries the boundary the run was accepted with.
It looks like an API key with another tag: `grt_<8-char prefix>_<secret>`. Only the SHA-256 of the secret is
stored (never the token), it expires after a short TTL and it can be revoked. The auth middleware accepts it only
for the routes of its own run (`/v1/sandbox/runs/{execution_id}/...`), so it opens nothing else. This module never
logs a token or a secret, and the token is hidden from `repr`.
"""
import json
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from core.database.tenant import DbPool, tenant_connection
from core.identity.keys import DUMMY_HASH, PREFIX_LENGTH, hash_secret, verify_secret
from core.identity.models import Principal, PrincipalKind, parse_scopes

logger = logging.getLogger("core.identity.run_tokens")

RUN_TOKEN_TAG = "grt"
MAX_TTL_SECONDS = 3600
_PREFIX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_TOKEN_RE = re.compile(rf"{RUN_TOKEN_TAG}_([a-z0-9]{{{PREFIX_LENGTH}}})_([A-Za-z0-9_-]{{32,128}})")


@dataclass(frozen=True)
class IssuedRunToken:
    token: str = field(repr=False)  # shown once, handed to the sandbox, never stored or logged
    token_id: UUID = field(default_factory=lambda: UUID(int=0))
    expires_at: datetime | None = None


@dataclass(frozen=True)
class RunGrant:
    """What a verified run token stands for: the principal that started the run, the run, and the fixed boundary."""

    principal: Principal
    execution_id: UUID
    boundary: dict[str, Any]
    token_id: UUID
    expires_at: datetime

    def covers(self, path: str) -> bool:
        """The run token opens the routes of its own run and nothing else."""
        return path.startswith(f"/v1/sandbox/runs/{self.execution_id}/")


def is_run_token(token: str) -> bool:
    return token.startswith(f"{RUN_TOKEN_TAG}_")


def parse_run_token(token: str) -> tuple[str, str] | None:
    match = _TOKEN_RE.fullmatch(token)  # fullmatch: a `$` anchor would accept a trailing newline
    return None if match is None else (match.group(1), match.group(2))


def generate_run_token() -> tuple[str, str, str]:
    """(prefix, token, secret_hash)."""
    prefix = "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(PREFIX_LENGTH))
    secret = secrets.token_urlsafe(32)
    return prefix, f"{RUN_TOKEN_TAG}_{prefix}_{secret}", hash_secret(secret)


async def issue_run_token(
    pool: DbPool, principal: Principal, execution_id: UUID, boundary: dict[str, Any], ttl_seconds: int,
) -> IssuedRunToken:
    """Write the token row (hash only) under the principal's tenant and return the token once."""
    ttl = max(1, min(int(ttl_seconds), MAX_TTL_SECONDS))
    prefix, token, secret_hash = generate_run_token()
    async with tenant_connection(pool, principal.tenant_id) as conn:
        row = await conn.fetchrow(
            "INSERT INTO run_tokens (tenant_id, execution_id, principal_id, prefix, secret_hash, scopes, boundary, expires_at, key_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW() + make_interval(secs => $8), $9) RETURNING id, expires_at",
            principal.tenant_id, execution_id, principal.id, prefix, secret_hash, sorted(principal.scopes),
            json.dumps(boundary), float(ttl), principal.credential_id,
        )
    if row is None:
        raise RuntimeError("the run token was not written")
    return IssuedRunToken(token=token, token_id=row["id"], expires_at=row["expires_at"])


async def authenticate_run_token(pool: DbPool, token: str) -> RunGrant | None:
    """The grant for a valid, unexpired, unrevoked token, or None. Raises only on infrastructure errors."""
    parsed = parse_run_token(token)
    if parsed is None:
        return None
    prefix, secret = parsed
    row = await pool.fetchrow("SELECT * FROM auth_lookup_run_token($1)", prefix)
    stored_hash: str = row["secret_hash"] if row is not None else DUMMY_HASH
    secret_ok = verify_secret(secret, stored_hash)  # always runs, so timing does not reveal the prefix
    if row is None or not secret_ok:
        return None
    if row["revoked_at"] is not None or row["principal_disabled_at"] is not None or row["key_revoked_at"] is not None or row["expires_at"] <= row["db_now"]:
        return None
    boundary = row["boundary"]
    return RunGrant(
        principal=Principal(
            id=row["principal_id"], tenant_id=row["tenant_id"], kind=cast(PrincipalKind, row["principal_kind"]),
            scopes=parse_scopes(cast(Any, row["scopes"])),
        ),
        execution_id=row["execution_id"],
        boundary=json.loads(boundary) if isinstance(boundary, (str, bytes)) else dict(boundary),
        token_id=row["token_id"],
        expires_at=row["expires_at"],
    )


async def revoke_run_tokens(pool: DbPool, tenant_id: UUID, execution_id: UUID) -> int:
    """Revoke every live token of a run (the run ended). Returns how many were revoked."""
    async with tenant_connection(pool, tenant_id) as conn:
        done = await conn.execute(
            "UPDATE run_tokens SET revoked_at = NOW() WHERE tenant_id = $1 AND execution_id = $2 AND revoked_at IS NULL",
            tenant_id, execution_id,
        )
    return int(done.rsplit(" ", 1)[-1])

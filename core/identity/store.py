"""Look up and verify an API key. Runs before the tenant is known.

The lookup goes through the SECURITY DEFINER function `auth_lookup_key(prefix)` (migration 0002),
the one audited row-level-security bypass. It returns only what verification needs. This module
never logs a token or secret.
"""
import logging
from typing import Any, cast

from asyncpg import Pool

from core.identity.keys import DUMMY_HASH, parse_key, verify_secret
from core.identity.models import Principal, PrincipalKind, parse_scopes

logger = logging.getLogger("core.identity.store")


async def authenticate_api_key(pool: Pool, token: str) -> Principal | None:
    """Return the Principal for a valid, unrevoked key, or None. Raises only on infrastructure errors."""
    parsed = parse_key(token)
    if parsed is None:
        return None
    prefix, secret = parsed
    row = await pool.fetchrow("SELECT * FROM auth_lookup_key($1)", prefix)
    stored_hash: str = row["secret_hash"] if row is not None else DUMMY_HASH
    secret_ok = verify_secret(secret, stored_hash)  # always runs, so timing does not reveal the prefix
    if row is None or not secret_ok:
        return None
    if row["revoked_at"] is not None or row["principal_disabled_at"] is not None:
        return None
    try:
        await pool.execute("SELECT auth_touch_key($1)", row["key_id"])
    except Exception:  # last_used_at is bookkeeping, it must not fail an authenticated request
        logger.warning("could not update last_used_at for key %s", row["key_id"], exc_info=True)
    return Principal(
        id=row["principal_id"],
        tenant_id=row["tenant_id"],
        kind=cast(PrincipalKind, row["principal_kind"]),
        scopes=parse_scopes(cast(Any, row["scopes"])),
    )


async def confirm_jwt_principal(pool: Pool, claimed: Principal) -> Principal | None:
    """Fail closed: a verified JWT is accepted only for an existing, non-disabled principal whose tenant
    equals the token's tenant claim. The kind comes from the database, scopes from the token.
    Raises only on infrastructure errors (the caller answers 503)."""
    row = await pool.fetchrow("SELECT * FROM auth_lookup_principal($1, $2)", claimed.id, claimed.tenant_id)
    if row is None or row["tenant_id"] != claimed.tenant_id or row["principal_disabled_at"] is not None:
        return None
    return Principal(
        id=row["principal_id"], tenant_id=row["tenant_id"],
        kind=cast(PrincipalKind, row["principal_kind"]), scopes=claimed.scopes,
    )

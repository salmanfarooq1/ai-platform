"""Administrative identity operations, run as the owner role (MIGRATION_DATABASE_URL).

Used by the CLI in scripts/admin/identity.py and by test fixtures. These are synchronous and are the
only place keys are created: the plaintext token is returned to the caller once and only its hash is
stored. Tenant-owned inserts run with `app.tenant_id` set, so they also satisfy row-level security
when the owner role is not a superuser.
"""
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg2
from psycopg2.extensions import connection as PgConnection

from core.identity.keys import GeneratedKey, generate_key
from core.identity.models import ALL_SCOPES, PRINCIPAL_KINDS


class AdminError(ValueError):
    """A bad argument or a missing record. The message is safe to print."""


@contextmanager
def admin_connection(dsn: str) -> Iterator[PgConnection]:
    conn = psycopg2.connect(dsn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _as_tenant(cur: Any, tenant_id: UUID) -> None:
    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))


def _returned_id(cur: Any) -> UUID:
    row = cur.fetchone()
    assert row is not None  # INSERT ... RETURNING always returns a row
    return UUID(str(row[0]))


def _tenant_id(cur: Any, slug: str) -> UUID:
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if row is None:
        raise AdminError(f"unknown tenant '{slug}'")
    return UUID(str(row[0]))


def create_tenant(
    conn: PgConnection, slug: str, name: str | None = None, *, default_kb: bool = True, deploy_shape: str,
) -> UUID:
    if not slug or not slug.replace("-", "").replace("_", "").isalnum():
        raise AdminError("tenant slug must be letters, digits, '-' or '_'")
    if deploy_shape not in {"single_tenant", "multi_tenant"}:
        raise AdminError("deploy shape must be single_tenant or multi_tenant")
    with conn.cursor() as cur:
        if deploy_shape == "single_tenant":
            cur.execute("SELECT pg_advisory_xact_lock(847204, 12)")
            cur.execute("SELECT count(*) FROM public.tenants")
            count_row = cur.fetchone()
            if count_row is None:
                raise AdminError("tenant count is unavailable")
            count = int(count_row[0])
            if count >= 1:
                raise AdminError("single_tenant deploy shape already contains a tenant; set DEPLOY_SHAPE=multi_tenant to add another")
        cur.execute("INSERT INTO tenants (slug, name) VALUES (%s, %s) RETURNING id", (slug, name or slug))
        tenant_id = _returned_id(cur)
        if default_kb:
            _as_tenant(cur, tenant_id)
            cur.execute(
                "INSERT INTO knowledge_bases (tenant_id, slug, description) VALUES (%s, 'default', %s)",
                (str(tenant_id), "Uncategorized or general documents"),
            )
    return tenant_id


def set_retention(conn: PgConnection, tenant_slug: str, days: int | None) -> None:
    """Set a tenant's own decision retention in days, or None to go back to the platform default."""
    if days is not None and days < 30:
        raise AdminError("retention must be at least 30 days")
    with conn.cursor() as cur:
        tenant_id = _tenant_id(cur, tenant_slug)
        cur.execute("UPDATE tenants SET retention_days = %s WHERE id = %s", (days, str(tenant_id)))


def create_kb(conn: PgConnection, tenant_slug: str, slug: str, description: str = "") -> UUID:
    with conn.cursor() as cur:
        tenant_id = _tenant_id(cur, tenant_slug)
        _as_tenant(cur, tenant_id)
        cur.execute(
            "INSERT INTO knowledge_bases (tenant_id, slug, description) VALUES (%s, %s, %s) RETURNING id",
            (str(tenant_id), slug, description),
        )
        return _returned_id(cur)


def list_kbs(conn: PgConnection, tenant_slug: str) -> list[dict[str, Any]]:
    """List a tenant's knowledge bases for operator inventory."""
    with conn.cursor() as cur:
        tenant_id = _tenant_id(cur, tenant_slug)
        _as_tenant(cur, tenant_id)
        cur.execute("SELECT id, slug, description FROM knowledge_bases WHERE tenant_id = %s ORDER BY slug", (str(tenant_id),))
        return [dict(zip(("id", "slug", "description"), row)) for row in cur.fetchall()]


def create_principal(conn: PgConnection, tenant_slug: str, kind: str, name: str) -> UUID:
    if kind not in PRINCIPAL_KINDS:
        raise AdminError(f"kind must be one of {', '.join(PRINCIPAL_KINDS)}")
    with conn.cursor() as cur:
        tenant_id = _tenant_id(cur, tenant_slug)
        _as_tenant(cur, tenant_id)
        cur.execute(
            "INSERT INTO principals (tenant_id, kind, name) VALUES (%s, %s, %s) RETURNING id",
            (str(tenant_id), kind, name),
        )
        return _returned_id(cur)


def list_principals(conn: PgConnection, tenant_slug: str) -> list[dict[str, Any]]:
    """List a tenant's principal metadata, including disabled principals."""
    with conn.cursor() as cur:
        tenant_id = _tenant_id(cur, tenant_slug)
        _as_tenant(cur, tenant_id)
        cur.execute("SELECT id, name, kind, disabled_at FROM principals WHERE tenant_id = %s ORDER BY id", (str(tenant_id),))
        return [dict(zip(("id", "name", "kind", "disabled_at"), row)) for row in cur.fetchall()]


def create_key(conn: PgConnection, principal_id: UUID | str, scopes: Iterable[str]) -> GeneratedKey:
    """Create a key for a principal. The returned token is the only copy of the secret."""
    wanted = sorted(set(scopes))
    unknown = [s for s in wanted if s not in ALL_SCOPES]
    if unknown or not wanted:
        raise AdminError(f"scopes must be a non-empty subset of {', '.join(sorted(ALL_SCOPES))}")
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id FROM principals WHERE id = %s", (str(principal_id),))
        row = cur.fetchone()
        if row is None:
            raise AdminError("unknown principal")
        tenant_id = UUID(str(row[0]))
        _as_tenant(cur, tenant_id)
        key = generate_key()
        cur.execute(
            "INSERT INTO api_keys (tenant_id, principal_id, prefix, secret_hash, scopes) VALUES (%s, %s, %s, %s, %s)",
            (str(tenant_id), str(principal_id), key.prefix, key.secret_hash, wanted),
        )
    return key


def revoke_key(conn: PgConnection, prefix: str) -> bool:
    """Revoke by prefix. Returns False if there is no such key or it was already revoked."""
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id FROM api_keys WHERE prefix = %s", (prefix,))
        row = cur.fetchone()
        if row is None:
            return False
        _as_tenant(cur, UUID(str(row[0])))
        cur.execute("UPDATE api_keys SET revoked_at = NOW() WHERE prefix = %s AND revoked_at IS NULL", (prefix,))
        return bool(cur.rowcount)


def list_keys(conn: PgConnection, tenant_slug: str | None = None, *, principal_id: UUID | str | None = None) -> list[dict[str, Any]]:
    """Return key metadata without secrets or hashes.

    A tenant slug establishes transaction-local RLS context before reading.
    None explicitly requests an operator-wide listing, subject to role visibility.
    """
    with conn.cursor() as cur:
        if tenant_slug is not None:
            _as_tenant(cur, _tenant_id(cur, tenant_slug))
        cur.execute(
            """
            SELECT k.prefix, t.slug, p.name, p.kind, k.scopes, k.created_at, k.last_used_at, k.revoked_at
            FROM api_keys k JOIN principals p ON p.id = k.principal_id JOIN tenants t ON t.id = k.tenant_id
            WHERE (%s::text IS NULL OR t.slug = %s)
              AND (%s::uuid IS NULL OR p.id = %s::uuid)
            ORDER BY k.created_at
            """,
            (tenant_slug, tenant_slug, str(principal_id) if principal_id is not None else None,
             str(principal_id) if principal_id is not None else None),
        )
        columns = ["prefix", "tenant", "principal", "kind", "scopes", "created_at", "last_used_at", "revoked_at"]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def inspect_credential(conn: PgConnection, token: str) -> dict[str, Any]:
    """Verify an active API key for an operator; return identity, never its secret/hash.

    This owner-role seam supports credential inventory and deployment validation.
    It does not grant runtime authority or accept a caller-supplied tenant.
    """
    from psycopg2.extras import RealDictCursor

    from core.identity.keys import parse_key, verify_secret

    parsed = parse_key(token)
    if parsed is None:
        raise AdminError("credential is invalid or inactive")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM auth_lookup_key(%s)", (parsed[0],))
        row = cur.fetchone()
        if (row is None or row["revoked_at"] is not None or row["principal_disabled_at"] is not None
                or not verify_secret(parsed[1], row["secret_hash"])):
            raise AdminError("credential is invalid or inactive")
        tenant_id = UUID(str(row["tenant_id"]))
        _as_tenant(cur, tenant_id)
        cur.execute("SELECT slug FROM tenants WHERE id = %s", (str(tenant_id),))
        tenant = cur.fetchone()
        if tenant is None:
            raise AdminError("credential is invalid or inactive")
        return {
            "tenant_id": str(tenant_id), "tenant_slug": tenant["slug"],
            "principal_id": str(row["principal_id"]), "principal_kind": row["principal_kind"],
            "prefix": parsed[0], "scopes": list(row["scopes"]),
        }

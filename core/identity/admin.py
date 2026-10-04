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


def create_tenant(conn: PgConnection, slug: str, name: str | None = None, default_kb: bool = True) -> UUID:
    if not slug or not slug.replace("-", "").replace("_", "").isalnum():
        raise AdminError("tenant slug must be letters, digits, '-' or '_'")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO tenants (slug, name) VALUES (%s, %s) RETURNING id", (slug, name or slug))
        tenant_id = _returned_id(cur)
        if default_kb:
            _as_tenant(cur, tenant_id)
            cur.execute(
                "INSERT INTO knowledge_bases (tenant_id, slug, description) VALUES (%s, 'default', %s)",
                (str(tenant_id), "Uncategorized or general documents"),
            )
    return tenant_id


def create_kb(conn: PgConnection, tenant_slug: str, slug: str, description: str = "") -> UUID:
    with conn.cursor() as cur:
        tenant_id = _tenant_id(cur, tenant_slug)
        _as_tenant(cur, tenant_id)
        cur.execute(
            "INSERT INTO knowledge_bases (tenant_id, slug, description) VALUES (%s, %s, %s) RETURNING id",
            (str(tenant_id), slug, description),
        )
        return _returned_id(cur)


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


def list_keys(conn: PgConnection, tenant_slug: str | None = None) -> list[dict[str, Any]]:
    """Key metadata only. Neither the secret nor its hash is returned."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT k.prefix, t.slug, p.name, p.kind, k.scopes, k.created_at, k.last_used_at, k.revoked_at
            FROM api_keys k JOIN principals p ON p.id = k.principal_id JOIN tenants t ON t.id = k.tenant_id
            WHERE (%s::text IS NULL OR t.slug = %s)
            ORDER BY k.created_at
            """,
            (tenant_slug, tenant_slug),
        )
        columns = ["prefix", "tenant", "principal", "kind", "scopes", "created_at", "last_used_at", "revoked_at"]
        return [dict(zip(columns, row)) for row in cur.fetchall()]

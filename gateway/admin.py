"""Policy administration, run as the owner role (the app role can only read policies).

`set_policy` validates the document, then appends a new version and makes it the only active one, in one
transaction. Old versions are kept (the table is append-only). Used by `scripts/admin/identity.py`.
"""
from typing import Any
from uuid import UUID

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import Json

from core.identity.admin import AdminError
from gateway.policy import KNOWN_TOOLS, PolicyError, parse_policy


class PolicyConflict(AdminError):
    """The active policy no longer matches the publisher's expected version."""


def _tenant(cur: Any, slug: str) -> UUID:
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if row is None:
        raise AdminError(f"unknown tenant '{slug}'")
    return UUID(str(row[0]))


def _as_tenant(cur: Any, tenant_id: UUID) -> None:
    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))


def set_policy(
    conn: PgConnection, tenant_slug: str, document: Any, created_by: str,
    expected_version: int | None = None,
) -> int:
    """Append a policy version in the caller's transaction.

    With `expected_version`, raise PolicyConflict unless it matches the active head
    (0 when no policy exists). None publishes unconditionally. The caller commits.
    """
    try:
        parsed = parse_policy(document)
    except PolicyError as exc:
        raise AdminError(str(exc)) from exc
    unknown = sorted(set(parsed.tool_arguments) - KNOWN_TOOLS)
    if unknown:
        raise AdminError(f"tool_arguments names tools the platform does not have: {', '.join(unknown)} (known: {', '.join(sorted(KNOWN_TOOLS))})")
    with conn.cursor() as cur:
        tenant_id = _tenant(cur, tenant_slug)
        _as_tenant(cur, tenant_id)
        # A stable tenant lock also serializes writers when no policy exists yet.
        cur.execute("SELECT id FROM tenants WHERE id = %s FOR UPDATE", (str(tenant_id),))
        cur.execute("SELECT version FROM policies WHERE tenant_id = %s AND active FOR UPDATE", (str(tenant_id),))
        active = cur.fetchone()
        active_version = int(active[0]) if active is not None else 0
        if expected_version is not None and active_version != expected_version:
            raise PolicyConflict(f"policy version changed: expected {expected_version}, active {active_version}")
        cur.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM policies WHERE tenant_id = %s", (str(tenant_id),))
        row = cur.fetchone()
        assert row is not None  # an aggregate always returns a row
        version = int(row[0])
        cur.execute("UPDATE policies SET active = FALSE WHERE tenant_id = %s AND active", (str(tenant_id),))
        cur.execute(
            "INSERT INTO policies (tenant_id, version, document, created_by, active) VALUES (%s, %s, %s, %s, TRUE)",
            (str(tenant_id), version, Json(parsed.model_dump(mode="json")), created_by),
        )
    return version


def show_policy(conn: PgConnection, tenant_slug: str) -> dict[str, Any] | None:
    """The tenant's active policy (version, document, created_by, created_at), or None."""
    with conn.cursor() as cur:
        tenant_id = _tenant(cur, tenant_slug)
        _as_tenant(cur, tenant_id)
        cur.execute(
            "SELECT version, document, created_by, created_at FROM policies WHERE tenant_id = %s AND active",
            (str(tenant_id),),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {"version": row[0], "document": row[1], "created_by": row[2], "created_at": row[3]}

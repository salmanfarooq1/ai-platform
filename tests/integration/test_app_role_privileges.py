"""Least privilege (migration 0004): the app role reads the identity tables and cannot write them,
even inside its own tenant where row-level security would otherwise allow it."""
from uuid import UUID

import asyncpg
import pytest

from core.database.tenant import tenant_connection
from core.identity.store import authenticate_api_key

DENIED = asyncpg.exceptions.InsufficientPrivilegeError


async def _as(pool, tenant, sql, *args):
    async with tenant_connection(pool, UUID(tenant.id)) as conn:
        return await conn.execute(sql, *args)


async def test_app_role_cannot_change_its_own_keys(db_pool, owner_pool, tenant_a):
    """The live finding: set scopes to admin and un-revoke a key from inside the tenant."""
    with pytest.raises(DENIED, match="permission denied for table api_keys"):
        await _as(db_pool, tenant_a, "UPDATE api_keys SET scopes = '{admin}', revoked_at = NULL")
    with pytest.raises(DENIED, match="permission denied for table api_keys"):
        await _as(db_pool, tenant_a, "DELETE FROM api_keys")
    with pytest.raises(DENIED, match="permission denied for table api_keys"):
        await _as(db_pool, tenant_a, "INSERT INTO api_keys (tenant_id, principal_id, prefix, secret_hash) "
                                     "VALUES ($1, $2, 'zzzzzzzz', 'h')", UUID(tenant_a.id), UUID(tenant_a.principal_id))
    assert await owner_pool.fetchval("SELECT count(*) FROM api_keys WHERE 'admin' = ANY(scopes)") == 0


@pytest.mark.parametrize("sql, table", [
    ("INSERT INTO knowledge_bases (tenant_id, slug) VALUES ('{t}', 'new-kb')", "knowledge_bases"),
    ("UPDATE knowledge_bases SET description = 'x'", "knowledge_bases"),
    ("DELETE FROM knowledge_bases", "knowledge_bases"),
    ("INSERT INTO principals (tenant_id, kind, name) VALUES ('{t}', 'user', 'x')", "principals"),
    ("UPDATE principals SET disabled_at = NULL, kind = 'user'", "principals"),
    ("DELETE FROM principals", "principals"),
    ("UPDATE tenants SET slug = 'x'", "tenants"),
    ("DELETE FROM tenants", "tenants"),
    ("INSERT INTO tenants (slug, name) VALUES ('evil', 'evil')", "tenants"),
])
async def test_app_role_cannot_write_the_other_identity_tables(db_pool, tenant_a, sql, table):
    with pytest.raises(DENIED, match=f"permission denied for table {table}"):
        await _as(db_pool, tenant_a, sql.format(t=tenant_a.id))


async def test_app_role_has_no_access_to_migration_state(db_pool):
    with pytest.raises(DENIED, match="permission denied for table alembic_version"):
        await db_pool.execute("UPDATE alembic_version SET version_num = '0001'")
    with pytest.raises(DENIED, match="permission denied for table alembic_version"):
        await db_pool.fetch("SELECT * FROM alembic_version")


async def test_app_role_cannot_truncate_identity_tables(db_pool, tenant_a):
    with pytest.raises(DENIED, match="permission denied"):
        await db_pool.execute("TRUNCATE api_keys")


async def test_app_role_can_still_read_identity_tables_inside_its_tenant(db_pool, tenant_a):
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        assert await conn.fetchval("SELECT count(*) FROM knowledge_bases") == 3
        assert await conn.fetchval("SELECT count(*) FROM principals") == 1
        assert await conn.fetchval("SELECT count(*) FROM api_keys") == 3
        assert await conn.fetchval("SELECT count(*) FROM tenants") == 1


async def test_app_role_keeps_write_access_to_the_data_tables(db_pool, owner_pool, tenant_a):
    t = UUID(tenant_a.id)
    async with tenant_connection(db_pool, t) as conn:
        await conn.execute("INSERT INTO usage_log (tenant_id, request_id, endpoint, model) VALUES ($1, 'r', '/e', 'm')", t)
        await conn.execute("INSERT INTO feedback (tenant_id, request_id, endpoint, rating) VALUES ($1, 'r', '/e', 'up')", t)
        await conn.execute("INSERT INTO document_registry (tenant_id, document_id, namespace, content_hash) "
                           "VALUES ($1, 'd', 'legal', $2)", t, "a" * 64)
        await conn.execute("UPDATE document_registry SET chunk_count = 2")
        await conn.execute("DELETE FROM document_registry")
    assert await owner_pool.fetchval("SELECT count(*) FROM usage_log") == 1


async def test_last_used_at_still_works_through_the_definer_function(db_pool, owner_pool, tenant_a):
    assert await authenticate_api_key(db_pool, tenant_a.tokens["full"]) is not None
    assert await owner_pool.fetchval("SELECT last_used_at FROM api_keys WHERE prefix = $1", tenant_a.prefixes["full"]) is not None


async def test_future_tables_do_not_get_automatic_grants(owner_pool):
    """Default privileges were removed: a table created later gets no automatic grant to the app role, so
    the migration that creates it must grant explicitly."""
    acl = await owner_pool.fetch(
        "SELECT defaclobjtype, defaclacl::text AS acl FROM pg_default_acl WHERE defaclnamespace = 'public'::regnamespace")
    assert [r for r in acl if "gap_app" in r["acl"]] == []


async def test_admin_cli_functions_still_work_as_the_owner(database_url, tenant_a):
    from core.identity.admin import admin_connection, create_kb, create_key, create_principal, revoke_key

    with admin_connection(database_url) as conn:
        create_kb(conn, "tenant-a", "extra", "x")
        pid = create_principal(conn, "tenant-a", "agent", "p2")
        key = create_key(conn, pid, ["query"])
        assert revoke_key(conn, key.prefix) is True

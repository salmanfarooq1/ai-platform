"""Row-level security against real Postgres, as the non-privileged app role (requirements 2, 3, 4).

`db_pool` connects as `gap_app`. A superuser bypasses RLS, so a suite that ran as `postgres` would pass
these isolation checks for the wrong reason. `test_isolation_checks_only_mean_something_as_the_app_role`
proves the difference with the same query run by both roles.
"""
from uuid import UUID, uuid4

import asyncpg
import pytest
from pgvector.asyncpg import register_vector

from core.database.tenant import tenant_connection
from tests.fakes import fake_embedding

TENANT_TABLES = ["documents", "document_registry", "usage_log", "feedback", "knowledge_bases", "principals", "api_keys"]
VECTOR = fake_embedding("hello")


async def _seed(owner_pool, tenant) -> None:
    """One row per tenant-owned table for `tenant` (knowledge bases, principals and api_keys exist already)."""
    tid = UUID(tenant.id)
    await owner_pool.execute(
        "INSERT INTO documents (tenant_id, document_id, namespace, content, embedding) VALUES ($1, $2, 'legal', $3, $4)",
        tid, f"{tenant.slug}.md", f"content of {tenant.slug}", VECTOR)
    await owner_pool.execute(
        "INSERT INTO document_registry (tenant_id, document_id, namespace, content_hash, chunk_count) "
        "VALUES ($1, $2, 'legal', $3, 1)", tid, f"{tenant.slug}.md", "a" * 64)
    await owner_pool.execute(
        "INSERT INTO usage_log (tenant_id, request_id, endpoint, model) VALUES ($1, $2, '/v1/search', 'm')",
        tid, f"req-{tenant.slug}")
    await owner_pool.execute(
        "INSERT INTO feedback (tenant_id, request_id, endpoint, rating) VALUES ($1, $2, '/v1/search', 'up')",
        tid, f"req-{tenant.slug}")


@pytest.fixture
async def seeded(owner_pool, tenants):
    for tenant in tenants:
        await _seed(owner_pool, tenant)
    return tenants


@pytest.fixture
async def app_conn_pool(app_database_url, clean_state):
    pool = await asyncpg.create_pool(dsn=app_database_url, min_size=1, max_size=1, init=register_vector,
                                     statement_cache_size=0)
    yield pool
    await pool.close()


async def test_app_connects_as_a_non_privileged_role(db_pool):
    row = await db_pool.fetchrow("SELECT current_user AS name, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    assert row["name"] == "gap_app"
    assert row["rolsuper"] is False
    assert row["rolbypassrls"] is False


async def test_isolation_checks_only_mean_something_as_the_app_role(db_pool, owner_pool, seeded):
    """The same query, no tenant set: the app role sees nothing, a superuser sees everything.
    If the suite connected as `postgres`, every isolation assertion here would fail."""
    for table in ("documents", "document_registry", "usage_log", "feedback", "knowledge_bases"):
        assert await db_pool.fetchval(f"SELECT count(*) FROM {table}") == 0, table
        assert await owner_pool.fetchval(f"SELECT count(*) FROM {table}") > 0, table


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_with_a_tenant_set_only_that_tenants_rows_are_visible(db_pool, owner_pool, seeded, table):
    a, b = seeded
    expected = {a.slug: await owner_pool.fetchval(f"SELECT count(*) FROM {table} WHERE tenant_id = $1", UUID(a.id)),
                b.slug: await owner_pool.fetchval(f"SELECT count(*) FROM {table} WHERE tenant_id = $1", UUID(b.id))}
    assert all(n > 0 for n in expected.values()), "fixture must give each tenant rows in every table"
    for tenant in (a, b):
        async with tenant_connection(db_pool, UUID(tenant.id)) as conn:
            rows = await conn.fetch(f"SELECT DISTINCT tenant_id FROM {table}")
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")
        assert [r["tenant_id"] for r in rows] == [UUID(tenant.id)]
        assert count == expected[tenant.slug]


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_missing_setting_returns_zero_rows_fail_closed(db_pool, seeded, table):
    assert await db_pool.fetchval(f"SELECT count(*) FROM {table}") == 0
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', '', true)")  # empty string behaves like unset
            assert await conn.fetchval(f"SELECT count(*) FROM {table}") == 0


async def test_tenants_table_exposes_only_the_callers_own_row(db_pool, seeded):
    a, _ = seeded
    assert await db_pool.fetchval("SELECT count(*) FROM tenants") == 0
    async with tenant_connection(db_pool, UUID(a.id)) as conn:
        assert [r["slug"] for r in await conn.fetch("SELECT slug FROM tenants")] == ["tenant-a"]


INSERTS = {
    "documents": ("INSERT INTO documents (tenant_id, document_id, namespace, content, embedding) "
                  "VALUES ($1, 'x.md', 'legal', 'x', $2)"),
    "document_registry": ("INSERT INTO document_registry (tenant_id, document_id, namespace, content_hash) "
                          "VALUES ($1, 'x.md', 'legal', $2)"),
    "usage_log": "INSERT INTO usage_log (tenant_id, request_id, endpoint, model) VALUES ($1, 'r', '/e', $2)",
    "feedback": "INSERT INTO feedback (tenant_id, request_id, endpoint, rating) VALUES ($1, 'r', '/e', $2)",
}
INSERT_ARGS = {"documents": VECTOR, "document_registry": "h" * 64, "usage_log": "m", "feedback": "up"}


@pytest.mark.parametrize("table", sorted(INSERTS))
async def test_inserting_a_row_for_another_tenant_is_rejected(db_pool, owner_pool, seeded, table):
    a, b = seeded
    before = await owner_pool.fetchval(f"SELECT count(*) FROM {table}")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="row-level security"):
        async with tenant_connection(db_pool, UUID(a.id)) as conn:
            await conn.execute(INSERTS[table], UUID(b.id), INSERT_ARGS[table])
    assert await owner_pool.fetchval(f"SELECT count(*) FROM {table}") == before


async def test_inserting_without_any_tenant_setting_is_rejected(db_pool, seeded):
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="row-level security"):
        await db_pool.execute(INSERTS["usage_log"], UUID(seeded[0].id), "m")


async def test_updating_or_deleting_another_tenants_rows_touches_nothing(db_pool, owner_pool, seeded):
    a, b = seeded
    async with tenant_connection(db_pool, UUID(a.id)) as conn:
        updated = await conn.execute("UPDATE documents SET content = 'pwned' WHERE tenant_id = $1", UUID(b.id))
        deleted = await conn.execute("DELETE FROM documents WHERE tenant_id = $1", UUID(b.id))
        moved = await conn.execute("DELETE FROM document_registry")  # unfiltered: still only A's row
    assert (updated, deleted, moved) == ("UPDATE 0", "DELETE 0", "DELETE 1")
    assert await owner_pool.fetchval("SELECT content FROM documents WHERE tenant_id = $1", UUID(b.id)) == "content of tenant-b"
    assert await owner_pool.fetchval("SELECT count(*) FROM document_registry") == 1


async def test_a_row_cannot_be_moved_to_another_tenant_by_update(db_pool, seeded):
    a, b = seeded
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="row-level security"):
        async with tenant_connection(db_pool, UUID(a.id)) as conn:
            await conn.execute("UPDATE documents SET tenant_id = $1", UUID(b.id))


async def test_retrieval_queries_without_a_tenant_filter_still_return_only_the_callers_rows(db_pool, seeded):
    """RLS holds even if application code forgets its WHERE tenant_id clause."""
    a, b = seeded
    async with tenant_connection(db_pool, UUID(b.id)) as conn:
        rows = await conn.fetch("SELECT document_id FROM documents WHERE namespace = 'legal'")
    assert [r["document_id"] for r in rows] == ["tenant-b.md"]
    assert a.slug not in rows[0]["document_id"]


async def test_the_tenant_setting_does_not_leak_to_the_next_user_of_a_pooled_connection(app_conn_pool, seeded):
    a, _ = seeded
    async with tenant_connection(app_conn_pool, UUID(a.id)) as conn:
        assert await conn.fetchval("SELECT count(*) FROM documents") == 1
    # pool max_size=1: this is the very same physical connection
    async with app_conn_pool.acquire() as conn:
        assert await conn.fetchval("SELECT current_setting('app.tenant_id', true)") in (None, "")
        assert await conn.fetchval("SELECT count(*) FROM documents") == 0


async def test_the_tenant_setting_is_rolled_back_with_the_transaction(app_conn_pool, seeded):
    a, _ = seeded
    with pytest.raises(RuntimeError):
        async with tenant_connection(app_conn_pool, UUID(a.id)):
            raise RuntimeError("boom")
    async with app_conn_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM documents") == 0


async def test_the_app_role_cannot_read_key_hashes_of_other_tenants(db_pool, seeded):
    a, b = seeded
    async with tenant_connection(db_pool, UUID(a.id)) as conn:
        prefixes = {r["prefix"] for r in await conn.fetch("SELECT prefix FROM api_keys")}
    assert prefixes == set(a.prefixes.values())
    assert not prefixes & set(b.prefixes.values())


async def test_unknown_tenant_id_sees_nothing(db_pool, seeded):
    async with tenant_connection(db_pool, uuid4()) as conn:
        for table in TENANT_TABLES:
            assert await conn.fetchval(f"SELECT count(*) FROM {table}") == 0, table

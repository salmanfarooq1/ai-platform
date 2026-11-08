"""Migration 0010 and the tables it adds, as the app role: `sandbox_events` (append-only, forced RLS, bounded detail) and
`run_tokens` (forced RLS, hash only, a narrow lookup function). Includes the hosted case of an owner role that is subject
to the forced policies."""
import json
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg
import psycopg2
import pytest

from core.database.tenant import tenant_connection
from tests import harness
from tests.integration.test_migration_0007 import _exec

pytestmark = pytest.mark.integration

DENIED = asyncpg.exceptions.InsufficientPrivilegeError


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_mig10_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def grants(dsn, table):
    return {g for (g,) in _exec(dsn, "SELECT privilege_type FROM information_schema.role_table_grants WHERE grantee = 'gap_app' AND table_name = %s", (table,))}


def test_the_new_tables_have_forced_rls_and_the_grants_the_blueprint_gives(blank_db):
    harness.migrate(blank_db)
    for table in ("sandbox_events", "run_tokens"):
        assert _exec(blank_db, "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (table,)) == [(True, True)]
    assert grants(blank_db, "sandbox_events") == {"SELECT", "INSERT"}  # append-only for the app role
    assert grants(blank_db, "run_tokens") == {"SELECT", "INSERT", "UPDATE"}  # UPDATE revokes; no DELETE
    assert _exec(blank_db, "SELECT has_function_privilege('gap_app', 'auth_lookup_run_token(text)', 'EXECUTE')") == [(True,)]
    assert _exec(blank_db, "SELECT has_function_privilege('public', 'auth_lookup_run_token(text)', 'EXECUTE')") == [(False,)]


def test_0010_works_for_a_non_superuser_owner_and_changes_nothing_that_came_before(blank_db):
    role, password = f"mig_owner_{secrets.token_hex(3)}", secrets.token_hex(8)
    admin = psycopg2.connect(harness.ADMIN_URL)
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s", (password,))
        _exec(blank_db, "CREATE EXTENSION IF NOT EXISTS vector")
        _exec(blank_db, f"GRANT ALL ON SCHEMA public TO {role}")
        host = harness.ADMIN_URL.split("@", 1)[1].rsplit("/", 1)[0]
        owner_dsn = f"postgresql://{role}:{password}@{host}/{blank_db.rsplit('/', 1)[1]}"
        harness.migrate(owner_dsn, "0010")
        assert _exec(owner_dsn, "SELECT version_num FROM alembic_version") == [("0010",)]
        # the lookup function runs as the owner, subject to the forced policy: the owner_access policy lets it read
        app = psycopg2.connect(harness.app_url(blank_db))
        try:
            with app.cursor() as cur:
                cur.execute("SELECT * FROM auth_lookup_run_token('zzzzzzzz')")
                assert cur.fetchall() == []  # no such token, and no error from the forced policy
        finally:
            app.close()
    finally:
        harness.drop_database(blank_db.rsplit("/", 1)[1])
        with admin.cursor() as cur:
            cur.execute(f"DROP ROLE IF EXISTS {role}")
        admin.close()


async def insert_event(pool, tenant, execution_id, kind="log", detail=None, at=None):
    async with tenant_connection(pool, UUID(tenant.id)) as conn:
        await conn.execute(
            "INSERT INTO sandbox_events (tenant_id, execution_id, kind, detail, at) VALUES ($1, $2, $3, $4::jsonb, $5)",
            UUID(tenant.id), execution_id, kind, json.dumps(detail or {}), at or datetime.now(timezone.utc),
        )


async def test_a_tenant_reads_only_its_own_events_and_cannot_write_for_another_tenant(db_pool, owner_pool, tenant_a, tenant_b):
    run = uuid4()
    await insert_event(db_pool, tenant_a, run, "start")
    await insert_event(db_pool, tenant_b, run, "network_denied", {"host": "x"})  # the same execution id, another tenant
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        assert [r["kind"] for r in await conn.fetch("SELECT kind FROM sandbox_events WHERE execution_id = $1", run)] == ["start"]
    async with tenant_connection(db_pool, UUID(tenant_b.id)) as conn:
        assert [r["kind"] for r in await conn.fetch("SELECT kind FROM sandbox_events WHERE execution_id = $1", run)] == ["network_denied"]
    assert await owner_pool.fetchval("SELECT count(*) FROM sandbox_events") == 2
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="row-level security"):
        async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:  # tenant A writes a row that says tenant B
            await conn.execute("INSERT INTO sandbox_events (tenant_id, execution_id, kind) VALUES ($1, $2, 'log')", UUID(tenant_b.id), run)
    async with db_pool.acquire() as conn:  # no tenant set at all: nothing is visible
        assert await conn.fetchval("SELECT count(*) FROM sandbox_events") == 0


async def test_events_cannot_be_changed_or_removed_by_the_app_role(db_pool, tenant_a):
    run = uuid4()
    await insert_event(db_pool, tenant_a, run, "network_denied", {"host": "x"})
    for sql in ("UPDATE sandbox_events SET kind = 'log'", "DELETE FROM sandbox_events", "TRUNCATE sandbox_events"):
        with pytest.raises(DENIED, match="permission denied"):
            async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
                await conn.execute(sql)


async def test_the_table_refuses_an_unknown_kind_and_a_detail_over_2_kib(db_pool, tenant_a):
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await insert_event(db_pool, tenant_a, uuid4(), "shell_command")
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await insert_event(db_pool, tenant_a, uuid4(), "log", {"message": "x" * 3000})
    await insert_event(db_pool, tenant_a, uuid4(), "log", {"message": "x" * 1900})


async def issue(pool, tenant, execution_id, prefix="abcdefgh", secret_hash="a" * 64, scopes=("agent",), expires="1 hour"):
    async with tenant_connection(pool, UUID(tenant.id)) as conn:
        return await conn.fetchval(
            "INSERT INTO run_tokens (tenant_id, execution_id, principal_id, prefix, secret_hash, scopes, boundary, expires_at) "
            f"VALUES ($1, $2, $3, $4, $5, $6, '{{}}'::jsonb, NOW() + interval '{expires}') RETURNING id",
            UUID(tenant.id), execution_id, UUID(tenant.principal_id), prefix, secret_hash, list(scopes),
        )


async def test_run_tokens_are_isolated_by_tenant_and_cannot_be_deleted(db_pool, tenant_a, tenant_b):
    run = uuid4()
    token_id = await issue(db_pool, tenant_a, run)
    async with tenant_connection(db_pool, UUID(tenant_b.id)) as conn:
        assert await conn.fetchval("SELECT count(*) FROM run_tokens") == 0
        assert await conn.execute("UPDATE run_tokens SET revoked_at = NOW()") == "UPDATE 0"  # not even visible to update
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        assert await conn.execute("UPDATE run_tokens SET revoked_at = NOW() WHERE id = $1", token_id) == "UPDATE 1"
    with pytest.raises(DENIED, match="permission denied"):
        async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
            await conn.execute("DELETE FROM run_tokens")


async def test_the_lookup_function_is_the_only_way_to_find_a_token_before_the_tenant_is_known(db_pool, tenant_a):
    run = uuid4()
    await issue(db_pool, tenant_a, run, prefix="lookup01")
    async with db_pool.acquire() as conn:  # no tenant set: the table is closed, the function is not
        assert await conn.fetchval("SELECT count(*) FROM run_tokens") == 0
        row = await conn.fetchrow("SELECT * FROM auth_lookup_run_token('lookup01')")
        assert await conn.fetchrow("SELECT * FROM auth_lookup_run_token('nosuch99')") is None
    assert row is not None and row["execution_id"] == run and str(row["tenant_id"]) == tenant_a.id
    assert str(row["principal_id"]) == tenant_a.principal_id and row["principal_kind"] == "service"
    assert set(row.keys()) == {"token_id", "tenant_id", "execution_id", "principal_id", "principal_kind", "secret_hash", "scopes",
                               "boundary", "expires_at", "revoked_at", "principal_disabled_at", "db_now", "key_revoked_at"}


async def test_a_prefix_is_unique(db_pool, tenant_a, tenant_b):
    await issue(db_pool, tenant_a, uuid4(), prefix="samepref")
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await issue(db_pool, tenant_b, uuid4(), prefix="samepref")

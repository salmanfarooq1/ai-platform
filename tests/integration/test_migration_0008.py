"""Migration 0008: the job tables, their grants, and the definer functions for an owner role that is subject to the
forced row-level security (the hosted case)."""
import secrets

import psycopg2
import pytest

from tests import harness
from tests.integration.test_migration_0007 import _exec

pytestmark = pytest.mark.integration


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_mig8_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def test_the_new_tables_have_forced_rls_and_the_app_role_gets_only_select_insert_update(blank_db):
    harness.migrate(blank_db)
    for table in ("jobs", "outbox", "processed_events"):
        assert _exec(blank_db, "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (table,)) == [(True, True)]
        grants = {g for (g,) in _exec(blank_db, "SELECT privilege_type FROM information_schema.role_table_grants WHERE grantee = 'gap_app' AND table_name = %s", (table,))}
        assert grants == {"SELECT", "INSERT", "UPDATE"}


def test_the_definer_functions_are_executable_by_the_app_role_only(blank_db):
    harness.migrate(blank_db, "0008")
    for sig in ("jobs_claim(text, integer)", "jobs_tenant_of_execution(uuid)", "outbox_pending(integer, integer)"):
        assert _exec(blank_db, "SELECT prosecdef FROM pg_proc WHERE oid = %s::regprocedure", (sig,)) == [(True,)]
        assert _exec(blank_db, "SELECT has_function_privilege('gap_app', %s, 'EXECUTE'), has_function_privilege('public', %s, 'EXECUTE')", (sig, sig)) == [(True, False)]


def test_0008_keeps_existing_data_and_the_claim_works_for_a_non_superuser_owner(blank_db):
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
        harness.migrate(owner_dsn)
        tenant = "00000000-0000-0000-0000-000000000001"  # the default tenant 0002 creates
        # as the owner with no tenant set, FORCE would hide the rows; the owner-only policy and the function open them
        conn = psycopg2.connect(owner_dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                cur.execute("INSERT INTO jobs (tenant_id, kind) VALUES (%s, 'ingest') RETURNING id", (tenant,))
                job_id = cur.fetchone()[0]
            with conn, conn.cursor() as cur:
                cur.execute("SELECT claimed_id, claimed_tenant FROM jobs_claim('w', 30)")
                assert cur.fetchone() == (job_id, tenant)
                cur.execute("SELECT count(*) FROM outbox_pending(10, 10)")
        finally:
            conn.close()
        # the app role, which is never the owner, still sees nothing without a tenant
        app = psycopg2.connect(harness.app_url(blank_db))
        try:
            with app.cursor() as cur:
                cur.execute("SELECT count(*) FROM jobs")
                assert cur.fetchone() == (0,)
        finally:
            app.close()
    finally:
        harness.drop_database(blank_db.rsplit("/", 1)[1])
        with admin.cursor() as cur:
            cur.execute(f"DROP ROLE IF EXISTS {role}")
        admin.close()

"""Migration 0009: the chain tables, the retention and metrics functions, and the seed rows, including for an owner
role that is subject to the forced row-level security (the hosted case)."""
import secrets
from uuid import uuid4

import psycopg2
import pytest

from evidence.chain import genesis_hash
from tests import harness
from tests.integration.test_migration_0007 import _exec

pytestmark = pytest.mark.integration


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_mig9_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def test_the_new_tables_have_the_right_rls_and_grants(blank_db):
    harness.migrate(blank_db)
    for table, grants in (("chain_heads", {"SELECT", "INSERT", "UPDATE"}), ("chain_checkpoints", {"SELECT"})):
        assert _exec(blank_db, "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (table,)) == [(True, True)]
        got = {g for (g,) in _exec(blank_db, "SELECT privilege_type FROM information_schema.role_table_grants WHERE grantee = 'gap_app' AND table_name = %s", (table,))}
        assert got == grants, table
    # eval_runs belongs to no tenant: the app role reads it and cannot write it
    got = {g for (g,) in _exec(blank_db, "SELECT privilege_type FROM information_schema.role_table_grants WHERE grantee = 'gap_app' AND table_name = 'eval_runs'")}
    assert got == {"SELECT"}
    # gateway_decisions is still append-only for the app role
    got = {g for (g,) in _exec(blank_db, "SELECT privilege_type FROM information_schema.role_table_grants WHERE grantee = 'gap_app' AND table_name = 'gateway_decisions'")}
    assert got == {"SELECT", "INSERT"}


def test_existing_tenants_get_a_genesis_checkpoint_and_a_head_and_old_rows_stay_unchained(blank_db):
    harness.migrate(blank_db, "0008")
    tenant = "00000000-0000-0000-0000-000000000001"  # the default tenant 0002 creates
    _exec(blank_db, "INSERT INTO gateway_decisions (tenant_id, request_id, trace_id, action, outcome, stage, reason) "
                    "VALUES (%s, 'r', 't', 'kb.read', 'allow', 'allow', 'allowed')", (tenant,))
    harness.migrate(blank_db)
    assert _exec(blank_db, "SELECT position, row_hash, reason FROM chain_checkpoints WHERE tenant_id = %s", (tenant,)) == [
        (0, genesis_hash(tenant), "genesis")]
    assert _exec(blank_db, "SELECT position, row_hash FROM chain_heads WHERE tenant_id = %s", (tenant,)) == [(0, genesis_hash(tenant))]
    assert _exec(blank_db, "SELECT chain_position, prev_hash, row_hash FROM gateway_decisions") == [(None, None, None)]
    assert _exec(blank_db, "SELECT retention_days FROM tenants") == [(None,)]


def test_0009_works_for_a_non_superuser_owner_including_the_purge_and_the_metrics_reads(blank_db):
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
        tenant = "00000000-0000-0000-0000-000000000001"
        # as the app role: write two old chained-looking rows through the owner, then purge through the function
        owner = psycopg2.connect(owner_dsn)
        try:
            with owner, owner.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                for pos in (1, 2):
                    cur.execute(
                        "INSERT INTO gateway_decisions (id, tenant_id, request_id, trace_id, action, outcome, stage, reason, created_at, "
                        "chain_position, prev_hash, row_hash) VALUES (%s, %s, 'r', 't', 'kb.read', 'allow', 'allow', 'allowed', "
                        "NOW() - interval '200 days', %s, repeat('0', 64), repeat(%s, 64))", (str(uuid4()), tenant, pos, str(pos)))
        finally:
            owner.close()
        app = psycopg2.connect(harness.app_url(blank_db))
        try:
            with app, app.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
                cur.execute("SELECT purged, checkpoint_position, checkpoint_hash FROM decisions_purge_batch(%s, 90, 10, 2, %s, 'sig', 'kid')", (tenant, "2" * 64))
                assert cur.fetchone() == (2, 2, "2" * 64)
            with app, app.cursor() as cur:
                cur.execute("SELECT count(*) FROM retention_due_tenants(90)")
                assert cur.fetchone() == (0,)
                cur.execute("SELECT count(*) FROM trust_jobs_by_status()")
                cur.execute("SELECT trust_outbox_lag()")
                assert cur.fetchone() == (0.0,)
        finally:
            app.close()
        assert _exec(owner_dsn, "SELECT count(*) FROM gateway_decisions") == [(0,)]
        assert _exec(owner_dsn, "SELECT position, reason, signature, key_id FROM chain_checkpoints ORDER BY position") == [
            (0, "genesis", None, None), (2, "purge", "sig", "kid")]
    finally:
        harness.drop_database(blank_db.rsplit("/", 1)[1])
        with admin.cursor() as cur:
            cur.execute(f"DROP ROLE IF EXISTS {role}")
        admin.close()

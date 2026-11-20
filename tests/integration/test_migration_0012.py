"""Migration 0012 (Sprint 015, a fix-round finding): `jobs.deferrals`, how often a job was put off rather than failed."""
import pytest

from tests import harness
from tests.integration.test_migration_0007 import _exec

pytestmark = pytest.mark.integration


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_mig12_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def test_the_column_is_added_with_zero_for_every_existing_job(blank_db):
    harness.migrate(blank_db, "0011")
    tenant = _exec(blank_db, "SELECT id FROM tenants ORDER BY created_at LIMIT 1")[0][0]
    _exec(blank_db, "INSERT INTO jobs (tenant_id, kind, status, payload) VALUES (%s, 'ingest', 'queued', '{}'::jsonb)", (tenant,))
    assert _exec(blank_db, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'jobs' AND column_name = 'deferrals'") == [(0,)]
    harness.migrate(blank_db, "0012")
    assert _exec(blank_db, "SELECT version_num FROM alembic_version") == [("0012",)]
    assert _exec(blank_db, "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
                           "WHERE table_name = 'jobs' AND column_name = 'deferrals'") == [("integer", "NO", "0")]
    assert _exec(blank_db, "SELECT deferrals FROM jobs") == [(0,)]


def test_the_count_cannot_go_negative_and_the_app_role_keeps_its_grants_and_rls(blank_db):
    harness.migrate(blank_db)
    assert _exec(blank_db, "SELECT has_column_privilege('gap_app', 'jobs', 'deferrals', 'UPDATE'), "
                           "has_column_privilege('gap_app', 'jobs', 'deferrals', 'SELECT')") == [(True, True)]
    assert _exec(blank_db, "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'jobs'") == [(True, True)]
    tenant = _exec(blank_db, "SELECT id FROM tenants ORDER BY created_at LIMIT 1")[0][0]
    with pytest.raises(Exception, match="deferrals"):
        _exec(blank_db, "INSERT INTO jobs (tenant_id, kind, status, payload, deferrals) VALUES (%s, 'ingest', 'queued', '{}'::jsonb, -1)", (tenant,))


def test_repeating_the_upgrade_is_a_no_op(blank_db):
    harness.migrate(blank_db)
    harness.migrate(blank_db)
    assert _exec(blank_db, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'jobs' AND column_name = 'deferrals'") == [(1,)]

"""The e2e server sweep preserves databases with a live server lease."""

import psycopg2

from scripts.e2e.serve import acquire_database_lease, sweep_leftover_databases
from tests import harness


def _database_exists(name: str) -> bool:
    conn = psycopg2.connect(harness.ADMIN_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)", (name,))
            return cur.fetchone()[0]
    finally:
        conn.close()


def test_sweep_keeps_database_with_live_lease():
    harness.require_postgres()
    name, _ = harness.create_database(prefix="gap_e2e_")
    lease = acquire_database_lease(name)
    try:
        sweep_leftover_databases()
        assert _database_exists(name)
    finally:
        lease.close()
        harness.drop_database(name)


def test_sweep_drops_database_after_owner_lease_closes():
    harness.require_postgres()
    name, _ = harness.create_database(prefix="gap_e2e_")
    lease = acquire_database_lease(name)
    lease.close()

    sweep_leftover_databases()

    assert not _database_exists(name)

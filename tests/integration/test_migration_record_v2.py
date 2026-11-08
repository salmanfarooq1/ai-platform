"""The 0011 migration preserves the old chain and narrows the app claim function."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg
import psycopg2
import pytest

from adapters.pg_evidence import PgDecisionSink
from core.identity.admin import admin_connection, create_principal, create_tenant
from evidence import chain
from ports import DecisionEntry
from tests import harness

pytestmark = pytest.mark.integration


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_record_v2_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def _exec(dsn, sql, params=()):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None
    finally:
        conn.close()


def _seed_v1_chain(dsn):
    tenant_slug = f"record-v2-{uuid4().hex[:8]}"
    with admin_connection(dsn) as conn:
        tenant_id = create_tenant(conn, tenant_slug, default_kb=False, deploy_shape="multi_tenant")
        principal_id = create_principal(conn, tenant_slug, "service", "record-v2")
    previous = chain.genesis_hash(tenant_id)
    ids = []
    at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for position in range(1, 4):
                decision_id = uuid4()
                record = chain.decision_record(
                    id=decision_id, tenant_id=tenant_id, principal_id=principal_id, request_id=f"legacy-{position}",
                    action="audit.read", resource="fixture", outcome="allow", stage="allow", reason="allowed",
                    policy_version=None, input_sha256=None, execution_id=None, created_at=at,
                )
                row_hash = chain.compute_row_hash(record, previous)
                cur.execute(
                    "INSERT INTO gateway_decisions (id, tenant_id, principal_id, request_id, trace_id, action, resource, "
                    "outcome, stage, reason, policy_version, input_hash, created_at, chain_position, prev_hash, row_hash) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (decision_id, tenant_id, principal_id, f"legacy-{position}", "legacy-trace", "audit.read", "fixture",
                     "allow", "allow", "allowed", None, None, at, position, previous, row_hash),
                )
                ids.append(decision_id)
                previous = row_hash
            cur.execute(
                "INSERT INTO chain_heads (tenant_id, position, row_hash) VALUES (%s, 3, %s) "
                "ON CONFLICT (tenant_id) DO UPDATE SET position = 3, row_hash = EXCLUDED.row_hash",
                (tenant_id, previous),
            )
    finally:
        conn.close()
    return tenant_id, principal_id, ids


@pytest.mark.asyncio
async def test_upgrade_keeps_v1_chain_and_adds_v2(blank_db):
    harness.migrate(blank_db, "0010")
    tenant_id, principal_id, old_ids = _seed_v1_chain(blank_db)
    harness.migrate(blank_db)
    app_pool = await asyncpg.create_pool(harness.app_url(blank_db), min_size=1, max_size=2)
    try:
        new_id = await PgDecisionSink(app_pool).write(DecisionEntry(
            tenant_id=tenant_id, principal_id=principal_id, request_id="new-v2", trace_id="v2-trace",
            action="audit.read", resource="fixture", outcome="allow", stage="allow", reason="allowed",
            policy_version=None, input_sha256=None, execution_id=None, extensions={},
        ))
    finally:
        await app_pool.close()
    rows = _exec(blank_db,
        "SELECT id::text, tenant_id::text, principal_id::text, request_id, action, resource, outcome, stage, reason, "
        "policy_version, input_hash, execution_id::text, created_at, record_version, extensions, chain_position, "
        "prev_hash, row_hash FROM gateway_decisions ORDER BY chain_position")
    assert [row[13] for row in rows] == [1, 1, 1, 2]
    assert [row[14] for row in rows] == [{}, {}, {}, {}]
    chain_rows = []
    for row in rows:
        record = chain.decision_record(
            id=row[0], tenant_id=row[1], principal_id=row[2], request_id=row[3], action=row[4], resource=row[5],
            outcome=row[6], stage=row[7], reason=row[8], policy_version=row[9], input_sha256=row[10],
            execution_id=row[11], created_at=row[12], record_version=row[13], extensions=row[14],
        )
        chain_rows.append(chain.ChainRow(row[15], row[16], row[17], record))
    assert [UUID(row[0]) for row in rows[:3]] == old_ids
    assert UUID(rows[3][0]) == new_id
    assert all(check.ok for check in chain.verify_chain(chain_rows, {0: chain.genesis_hash(tenant_id)}))


def test_v1_row_with_extensions_is_rejected_by_the_database(blank_db):
    harness.migrate(blank_db, "0010")
    _, _, old_ids = _seed_v1_chain(blank_db)
    harness.migrate(blank_db)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _exec(blank_db, "UPDATE gateway_decisions SET extensions = '{\"x\":1}'::jsonb WHERE id = %s", (old_ids[0],))


def test_old_unfiltered_claim_is_not_executable_by_app(blank_db):
    harness.migrate(blank_db)
    assert _exec(blank_db,
        "SELECT has_function_privilege('gap_app', 'jobs_claim(text, integer)', 'EXECUTE'), "
        "has_function_privilege('gap_app', 'jobs_claim(text, integer, text[])', 'EXECUTE'), "
        "has_function_privilege('public', 'jobs_claim(text, integer)', 'EXECUTE'), "
        "has_function_privilege('public', 'jobs_claim(text, integer, text[])', 'EXECUTE')") == [(False, True, False, False)]

"""Alembic migrations against a real Postgres: empty database and the hosted-DB case."""
from pathlib import Path

import psycopg2
import pytest
from alembic import command

from tests import harness

LEGACY_SCHEMA = Path(__file__).parent / "fixtures" / "legacy_schema.sql"
BASELINE_TABLES = {"documents", "document_registry", "usage_log", "feedback"}
IDENTITY_TABLES = {"tenants", "principals", "api_keys", "knowledge_bases"}
GATEWAY_TABLES = {"policies", "gateway_decisions"}
JOB_TABLES = {"jobs", "outbox", "processed_events"}
TRUST_TABLES = {"chain_heads", "chain_checkpoints", "eval_runs"}  # Sprint 008
SANDBOX_TABLES = {"sandbox_events", "run_tokens"}  # Sprint 009
TENANT_OWNED = ["documents", "document_registry", "usage_log", "feedback"]
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_mig_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def _query(dsn, sql):
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def _snapshot(dsn):
    """Everything `\\d` shows, as data: columns, indexes, triggers, function body."""
    columns = _query(dsn, """
        SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name <> 'alembic_version'
        ORDER BY table_name, ordinal_position
    """)
    indexes = _query(dsn, "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                          "AND tablename <> 'alembic_version' ORDER BY 1, 2")
    triggers = _query(dsn, "SELECT tgrelid::regclass::text, tgname, pg_get_triggerdef(oid) FROM pg_trigger "
                           "WHERE NOT tgisinternal ORDER BY 1, 2")
    constraints = _query(dsn, "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint "
                              "WHERE connamespace = 'public'::regnamespace AND conrelid::regclass::text <> 'alembic_version' "
                              "ORDER BY 1, 2")
    function = _query(dsn, "SELECT pg_get_functiondef('update_fts_vector'::regproc)")
    return {"columns": columns, "indexes": indexes, "triggers": triggers, "constraints": constraints, "function": function}


def test_empty_database_reaches_head(blank_db):
    harness.migrate(blank_db)
    tables = {r[0] for r in _query(blank_db, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert tables == BASELINE_TABLES | IDENTITY_TABLES | GATEWAY_TABLES | JOB_TABLES | TRUST_TABLES | SANDBOX_TABLES | {"alembic_version"}
    assert _query(blank_db, "SELECT version_num FROM alembic_version") == [("0010",)]
    assert _query(blank_db, "SELECT extname FROM pg_extension WHERE extname = 'vector'") == [("vector",)]
    index_names = {r[0] for r in _query(blank_db, "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}
    # 0002 replaces the namespace-only indexes with indexes that lead with tenant_id.
    assert {"idx_documents_embedding_hnsw", "idx_documents_fts", "idx_documents_tenant_ns_docid",
            "idx_usage_log_tenant_created", "idx_feedback_request_id", "idx_feedback_tenant_created"} <= index_names
    assert not {"idx_documents_ns_docid", "idx_documents_namespace", "idx_usage_log_created"} & index_names
    assert {r[0] for r in _query(blank_db, "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")} == {
        "trig_update_fts", "trg_policies_append_only"}  # 0005 adds the append-only guard on policies
    dim = _query(blank_db, "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'documents'::regclass AND attname = 'embedding'")
    assert dim == [(768,)]


def test_upgrade_is_repeatable(blank_db):
    harness.migrate(blank_db)
    before = _snapshot(blank_db)
    harness.migrate(blank_db)  # second run is a no-op
    assert _snapshot(blank_db) == before
    assert _query(blank_db, "SELECT count(*) FROM alembic_version") == [(1,)]


def test_database_built_from_old_schema_reaches_head_with_no_table_changes(blank_db):
    conn = psycopg2.connect(blank_db)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(LEGACY_SCHEMA.read_text())
        # Rows that exist on the hosted database must survive.
        cur.execute("INSERT INTO document_registry (document_id, namespace, content_hash, chunk_count, source_filename) "
                    "VALUES ('kept.md', 'kyc_aml', %s, 3, 'kept.md')", ("a" * 64,))
        cur.execute("INSERT INTO documents (document_id, namespace, content) VALUES ('kept.md', 'kyc_aml', 'hello world')")
    conn.close()
    assert "alembic_version" not in {r[0] for r in _query(blank_db, "SELECT tablename FROM pg_tables WHERE schemaname='public'")}

    before = _snapshot(blank_db)
    harness.migrate(blank_db, "0001")  # the baseline revision: it must change no table
    after = _snapshot(blank_db)

    assert after == before
    assert _query(blank_db, "SELECT version_num FROM alembic_version") == [("0001",)]
    assert _query(blank_db, "SELECT document_id, chunk_count FROM document_registry") == [("kept.md", 3)]
    # The FTS trigger still works on the existing table.
    assert _query(blank_db, "SELECT fts_vector IS NOT NULL FROM documents WHERE document_id = 'kept.md'") == [(True,)]


def test_old_schema_and_fresh_migration_produce_identical_schemas(blank_db):
    harness.require_postgres()
    legacy_name, legacy_dsn = harness.create_database(prefix="gap_mig_legacy_")
    try:
        conn = psycopg2.connect(legacy_dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(LEGACY_SCHEMA.read_text())
        conn.close()
        harness.migrate(blank_db, "0001")  # the baseline revision must equal the old hand-written schema
        assert _snapshot(blank_db) == _snapshot(legacy_dsn)
    finally:
        harness.drop_database(legacy_name)


def _seed_pre_identity_rows(dsn):
    """Rows as they exist on the hosted database before Sprint 003."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        for ns, doc in (("legal", "gdpr.md"), ("legal", "ccpa.md"), ("kyc_aml", "bsa.md")):
            cur.execute("INSERT INTO document_registry (document_id, namespace, content_hash, chunk_count, source_filename) "
                        "VALUES (%s, %s, %s, 2, %s)", (doc, ns, "b" * 64, doc))
            for i in range(2):
                cur.execute("INSERT INTO documents (document_id, namespace, content) VALUES (%s, %s, %s)",
                            (doc, ns, f"chunk {i} of {doc} about breach"))
        for i in range(3):
            cur.execute("INSERT INTO usage_log (request_id, endpoint, namespace, model) VALUES (%s, '/search', 'legal', 'm')", (f"r{i}",))
        cur.execute("INSERT INTO feedback (request_id, endpoint, rating) VALUES ('r0', '/search', 'up')")
    conn.close()


def _counts(dsn):
    return {t: _query(dsn, f"SELECT count(*) FROM {t}")[0][0] for t in TENANT_OWNED}


def _assert_backfilled(dsn, before):
    assert _query(dsn, "SELECT version_num FROM alembic_version") == [("0010",)]
    assert _counts(dsn) == before == {"documents": 6, "document_registry": 3, "usage_log": 3, "feedback": 1}
    for table in TENANT_OWNED:
        assert _query(dsn, f"SELECT DISTINCT tenant_id::text FROM {table}") == [(DEFAULT_TENANT_ID,)]
        assert _query(dsn, f"SELECT is_nullable FROM information_schema.columns "
                           f"WHERE table_name = '{table}' AND column_name = 'tenant_id'") == [("NO",)]
    assert _query(dsn, "SELECT slug FROM tenants") == [("default",)]
    assert _query(dsn, "SELECT slug FROM knowledge_bases ORDER BY slug") == [("default",), ("kyc_aml",), ("legal",)]
    pk = _query(dsn, "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                     "WHERE conrelid = 'document_registry'::regclass AND contype = 'p'")
    assert pk == [("PRIMARY KEY (tenant_id, namespace, document_id)",)]
    assert _query(dsn, "SELECT fts_vector IS NOT NULL FROM documents WHERE document_id = 'bsa.md' LIMIT 1") == [(True,)]


def test_upgrade_from_0001_with_existing_rows_keeps_counts_and_backfills_default_tenant(blank_db):
    harness.migrate(blank_db, "0001")
    _seed_pre_identity_rows(blank_db)
    before = _counts(blank_db)

    harness.migrate(blank_db)

    _assert_backfilled(blank_db, before)


def test_hosted_database_without_alembic_history_reaches_0002_and_backfills(blank_db):
    """The hosted case: tables exist from the old schema.sql, no alembic_version table."""
    conn = psycopg2.connect(blank_db)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(LEGACY_SCHEMA.read_text())
    conn.close()
    _seed_pre_identity_rows(blank_db)
    before = _counts(blank_db)

    harness.migrate(blank_db)

    _assert_backfilled(blank_db, before)


def test_rls_is_enabled_everywhere_and_forced_where_the_owner_is_not_exempt(blank_db):
    harness.migrate(blank_db)
    rows = dict((name, (enabled, forced)) for name, enabled, forced in _query(
        blank_db, "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                  "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"))
    for table in ("documents", "document_registry", "usage_log", "feedback", "knowledge_bases"):
        assert rows[table] == (True, True), table
    # Owner-exempt on purpose: the SECURITY DEFINER lookup functions read these before a tenant is known.
    for table in ("principals", "api_keys", "tenants"):
        assert rows[table] == (True, False), table
    policy = _query(blank_db, "SELECT qual, with_check FROM pg_policies WHERE tablename = 'documents'")
    assert policy == [("(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)",
                       "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)")]


def test_0003_adds_the_principal_lookup_function_for_the_app_role_only(blank_db):
    harness.migrate(blank_db)
    assert _query(blank_db, "SELECT prosecdef FROM pg_proc WHERE proname = 'auth_lookup_principal'") == [(True,)]
    assert _query(blank_db, "SELECT has_function_privilege('gap_app', 'auth_lookup_principal(uuid, uuid)', 'EXECUTE')") == [(True,)]
    assert _query(blank_db, "SELECT has_function_privilege('public', 'auth_lookup_principal(uuid, uuid)', 'EXECUTE')") == [(False,)]


def test_downgrade_is_refused(blank_db):
    harness.migrate(blank_db)
    with pytest.raises(NotImplementedError, match="forward-only"):
        command.downgrade(harness.alembic_config(blank_db), "base")

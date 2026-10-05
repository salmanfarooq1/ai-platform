"""Migration 0007 on data from 0005: counts are kept, every vector gets a model and dimension, run provenance is added.

Also against an owner role that is subject to the forced row-level security (the hosted case), where a plain
UPDATE or count of `documents` without a tenant setting would silently see no rows.
"""
import secrets

import psycopg2
import pytest

from core.identity.admin import admin_connection, create_kb, create_tenant
from core.settings import get_settings
from tests import harness

VECTOR_SQL = "('[' || array_to_string(array_fill(0, ARRAY[768]), ',') || ']')::vector"


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_mig7_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def _exec(dsn, sql, params=None):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None
    finally:
        conn.close()


def seed_0005(dsn):
    """Two tenants with chunks and decisions, as they exist before this sprint. Returns the ids."""
    ids = {}
    with admin_connection(dsn) as conn:
        for slug, docs in (("tenant-a", 3), ("tenant-b", 2)):
            ids[slug] = (create_tenant(conn, slug, default_kb=False), docs)
            create_kb(conn, slug, "legal", "legal")
    for slug, (tenant_id, docs) in ids.items():
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                for i in range(docs):
                    cur.execute(
                        f"INSERT INTO documents (tenant_id, document_id, namespace, content, embedding) "
                        f"VALUES (%s, %s, 'legal', %s, {VECTOR_SQL})", (str(tenant_id), f"{slug}-{i}.md", f"chunk {i}"))
                cur.execute(
                    "INSERT INTO gateway_decisions (tenant_id, request_id, trace_id, action, outcome, stage, reason) "
                    "VALUES (%s, 'r-1', 't-1', 'kb.read', 'allow', 'allow', 'allowed')", (str(tenant_id),))
            conn.commit()
        finally:
            conn.close()
    return ids


def test_0007_keeps_every_row_and_gives_each_chunk_the_configured_model_and_dimension(blank_db):
    harness.migrate(blank_db, "0005")
    ids = seed_0005(blank_db)
    assert _exec(blank_db, "SELECT count(*) FROM documents") == [(5,)]
    assert "embedding_model" not in {r[0] for r in _exec(
        blank_db, "SELECT column_name FROM information_schema.columns WHERE table_name = 'documents'")}

    harness.migrate(blank_db)

    settings = get_settings()
    assert _exec(blank_db, "SELECT count(*) FROM documents") == [(5,)]  # nothing lost
    assert _exec(blank_db, "SELECT count(*) FROM gateway_decisions") == [(2,)]
    per_tenant = _exec(blank_db, "SELECT tenant_id::text, count(*) FROM documents GROUP BY 1 ORDER BY 2")
    assert sorted(per_tenant, key=lambda r: r[1]) == sorted(
        [(str(tid), n) for tid, n in ids.values()], key=lambda r: r[1])
    assert _exec(blank_db, "SELECT DISTINCT embedding_model, embedding_dim FROM documents") == [
        (settings.embed_model, settings.embedding_dim)]
    assert _exec(blank_db, "SELECT count(*) FROM documents WHERE embedding_model IS NULL OR embedding_dim IS NULL") == [(0,)]


def test_0007_refuses_a_vector_width_that_differs_from_the_configured_dimension_and_changes_nothing(blank_db, monkeypatch):
    from types import SimpleNamespace

    harness.migrate(blank_db, "0005")
    seed_0005(blank_db)  # five vectors of width 768
    real = get_settings()
    monkeypatch.setattr("core.settings.get_settings", lambda: SimpleNamespace(embed_model=real.embed_model, embedding_dim=1536))

    with pytest.raises(RuntimeError, match=r"EMBEDDING_DIM is 1536 but documents holds 5 vector\(s\) of width 768"):
        harness.migrate(blank_db)

    columns = {r[0] for r in _exec(blank_db, "SELECT column_name FROM information_schema.columns WHERE table_name = 'documents'")}
    assert "embedding_model" not in columns and "embedding_dim" not in columns  # nothing was added or mislabelled
    assert _exec(blank_db, "SELECT version_num FROM alembic_version") == [("0005",)]  # 0007 rolled back
    assert _exec(blank_db, "SELECT count(*) FROM documents") == [(5,)]


def test_0007_labels_each_row_with_the_real_vector_width(blank_db):
    harness.migrate(blank_db, "0005")
    seed_0005(blank_db)
    harness.migrate(blank_db)
    assert _exec(blank_db, "SELECT DISTINCT embedding_dim FROM documents") == [(768,)]
    assert _exec(blank_db, "SELECT count(*) FROM documents WHERE embedding_dim <> vector_dims(embedding)") == [(0,)]


def test_0007_makes_the_columns_not_null_adds_the_indexes_and_a_nullable_execution_id(blank_db):
    harness.migrate(blank_db)
    nullable = dict(_exec(blank_db, "SELECT column_name, is_nullable FROM information_schema.columns "
                                    "WHERE table_name = 'documents' AND column_name IN ('embedding_model', 'embedding_dim')"))
    assert nullable == {"embedding_model": "NO", "embedding_dim": "NO"}
    assert _exec(blank_db, "SELECT data_type, is_nullable FROM information_schema.columns "
                           "WHERE table_name = 'gateway_decisions' AND column_name = 'execution_id'") == [("uuid", "YES")]
    indexes = {r[0]: r[1] for r in _exec(blank_db, "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")}
    assert "embedding_model" in indexes["idx_documents_embedding_provenance"]
    assert "execution_id" in indexes["idx_gateway_decisions_execution"]


def test_0007_does_not_change_the_grants_of_the_app_role_on_the_tables(blank_db):
    harness.migrate(blank_db, "0006")
    before = _exec(blank_db, "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                             "WHERE grantee = 'gap_app' ORDER BY 1, 2")
    harness.migrate(blank_db)
    assert _exec(blank_db, "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                           "WHERE grantee = 'gap_app' ORDER BY 1, 2") == before


def test_count_stale_vectors_is_a_narrow_definer_function_for_the_app_role(blank_db):
    harness.migrate(blank_db)
    assert _exec(blank_db, "SELECT prosecdef FROM pg_proc WHERE proname = 'count_stale_vectors'") == [(True,)]
    assert _exec(blank_db, "SELECT has_function_privilege('gap_app', 'count_stale_vectors(text, integer)', 'EXECUTE')") == [(True,)]
    assert _exec(blank_db, "SELECT has_function_privilege('public', 'count_stale_vectors(text, integer)', 'EXECUTE')") == [(False,)]


def test_count_stale_vectors_counts_across_tenants_and_restores_the_tenant_setting(blank_db):
    harness.migrate(blank_db, "0005")
    seed_0005(blank_db)
    harness.migrate(blank_db)
    settings = get_settings()
    conn = psycopg2.connect(blank_db)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count_stale_vectors(%s, %s)", (settings.embed_model, settings.embedding_dim))
            assert cur.fetchone() == (0,)
            cur.execute("SELECT count_stale_vectors('some/other-model', %s)", (settings.embedding_dim,))
            assert cur.fetchone() == (5,)
            cur.execute("SELECT count_stale_vectors(%s, 1536)", (settings.embed_model,))
            assert cur.fetchone() == (5,)
            cur.execute("SELECT set_config('app.tenant_id', '11111111-1111-1111-1111-111111111111', true)")
            cur.execute("SELECT count_stale_vectors('x', 1)")
            cur.execute("SELECT current_setting('app.tenant_id', true)")
            assert cur.fetchone() == ("11111111-1111-1111-1111-111111111111",)  # the caller's setting is put back
    finally:
        conn.close()


def test_0007_also_works_for_an_owner_role_that_is_subject_to_row_level_security(blank_db):
    """The hosted case: the migration role is not a superuser and has no BYPASSRLS, and it owns the tables, which
    are FORCEd. Every migration up to 0007 runs as that role, and a plain UPDATE or count of `documents` without a
    tenant setting would see no rows for it."""
    role, password = f"mig_owner_{secrets.token_hex(3)}", secrets.token_hex(8)
    admin = psycopg2.connect(harness.ADMIN_URL)
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %s", (password,))
        _exec(blank_db, "CREATE EXTENSION IF NOT EXISTS vector")  # an extension needs a superuser, as on a hosted database
        _exec(blank_db, f"GRANT ALL ON SCHEMA public TO {role}")
        host = harness.ADMIN_URL.split("@", 1)[1].rsplit("/", 1)[0]
        owner_dsn = f"postgresql://{role}:{password}@{host}/{blank_db.rsplit('/', 1)[1]}"
        assert _exec(owner_dsn, "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user") == [(False,)]

        harness.migrate(owner_dsn, "0005")
        seed_0005(owner_dsn)
        assert _exec(owner_dsn, "SELECT count(*) FROM documents") == [(0,)]  # forced RLS hides the rows from the owner too
        assert _exec(blank_db, "SELECT count(*) FROM documents") == [(5,)]  # (the superuser sees them)

        harness.migrate(owner_dsn)

        settings = get_settings()
        assert _exec(blank_db, "SELECT count(*) FROM documents") == [(5,)]
        assert _exec(blank_db, "SELECT DISTINCT embedding_model, embedding_dim FROM documents") == [
            (settings.embed_model, settings.embedding_dim)]  # every row backfilled, though the owner cannot see them
        assert _exec(owner_dsn, "SELECT count_stale_vectors('some/other-model', %s)", (settings.embedding_dim,)) == [(5,)]
        assert _exec(owner_dsn, "SELECT count_stale_vectors(%s, %s)", (settings.embed_model, settings.embedding_dim)) == [(0,)]
    finally:
        harness.drop_database(blank_db.rsplit("/", 1)[1])
        with admin.cursor() as cur:
            cur.execute(f"DROP ROLE IF EXISTS {role}")
        admin.close()

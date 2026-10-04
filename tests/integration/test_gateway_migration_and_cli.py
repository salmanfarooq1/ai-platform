"""Migration 0005 on a database at 0004 that holds data, and the policy admin CLI."""
import json
import re

import psycopg2
import pytest

from scripts.admin.identity import main
from tests import harness
from tests.integration.test_migrations import (  # noqa: F401 - blank_db is a fixture
    TENANT_OWNED,
    _counts,
    _query,
    _seed_pre_identity_rows,
    blank_db,
)

NEW_TABLES = ("policies", "gateway_decisions")


def test_0005_applies_on_a_database_at_0004_with_data_and_loses_nothing(blank_db):  # noqa: F811 - pytest fixture injection
    harness.migrate(blank_db, "0001")
    _seed_pre_identity_rows(blank_db)
    harness.ensure_app_role()
    harness.migrate(blank_db, "0004")
    assert _query(blank_db, "SELECT version_num FROM alembic_version") == [("0004",)]
    # a tenant of its own, with data, on top of the default tenant's backfilled rows
    conn = psycopg2.connect(blank_db)
    with conn, conn.cursor() as cur:  # `with conn` commits
        cur.execute("INSERT INTO tenants (slug, name) VALUES ('acme', 'Acme') RETURNING id")
        acme = cur.fetchone()[0]
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(acme),))
        cur.execute("INSERT INTO knowledge_bases (tenant_id, slug) VALUES (%s, 'acme_kb')", (acme,))
    conn.close()
    before = {**_counts(blank_db), "tenants": _query(blank_db, "SELECT count(*) FROM tenants")[0][0],
              "knowledge_bases": _query(blank_db, "SELECT count(*) FROM knowledge_bases")[0][0]}
    assert before["documents"] == 6 and before["tenants"] == 2
    snapshot = {t: _query(blank_db, f"SELECT md5(string_agg(x::text, '|' ORDER BY x::text)) FROM {t} x") for t in TENANT_OWNED}

    harness.migrate(blank_db, "0005")

    assert _query(blank_db, "SELECT version_num FROM alembic_version") == [("0005",)]
    after = {**_counts(blank_db), "tenants": _query(blank_db, "SELECT count(*) FROM tenants")[0][0],
             "knowledge_bases": _query(blank_db, "SELECT count(*) FROM knowledge_bases")[0][0]}
    assert after == before  # no row lost or added
    assert {t: _query(blank_db, f"SELECT md5(string_agg(x::text, '|' ORDER BY x::text)) FROM {t} x") for t in TENANT_OWNED} == snapshot
    for table in NEW_TABLES:
        assert _query(blank_db, f"SELECT count(*) FROM {table}") == [(0,)]
    rows = dict((n, (e, f)) for n, e, f in _query(
        blank_db, "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relnamespace = 'public'::regnamespace "
                  "AND relname IN ('policies', 'gateway_decisions')"))
    assert rows == {"policies": (True, True), "gateway_decisions": (True, True)}


def test_0005_grants_the_app_role_explicitly_and_only_what_it_needs(blank_db):  # noqa: F811
    harness.ensure_app_role()
    harness.migrate(blank_db)
    privs = {
        (table, priv): _query(blank_db, f"SELECT has_table_privilege('gap_app', '{table}', '{priv}')")[0][0]
        for table in NEW_TABLES for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
    }
    assert {k for k, v in privs.items() if v} == {("policies", "SELECT"), ("gateway_decisions", "SELECT"), ("gateway_decisions", "INSERT")}


def test_0005_upgrade_is_repeatable(blank_db):  # noqa: F811
    harness.migrate(blank_db)
    first = _query(blank_db, "SELECT indexname FROM pg_indexes WHERE tablename IN ('policies', 'gateway_decisions') ORDER BY 1")
    harness.migrate(blank_db)
    assert _query(blank_db, "SELECT indexname FROM pg_indexes WHERE tablename IN ('policies', 'gateway_decisions') ORDER BY 1") == first
    assert {"idx_policies_one_active", "idx_gateway_decisions_tenant_created", "idx_gateway_decisions_tenant_request"} <= {r[0] for r in first}


# ------------------------------------------------------------------ admin CLI

@pytest.fixture
def cli(database_url, clean_state, capsys, tenants):
    def run(*args):
        code = main(["--dsn", database_url, *args])
        out = capsys.readouterr()
        return code, out.out, out.err

    return run


def test_set_policy_and_show_policy(cli, tmp_path, database_url):
    document = {"allowed_kbs": ["legal"], "allowed_models": ["gemini/x"], "allowed_tools": ["retrieve_chunks"],
                "max_tool_calls": 2, "blocked_terms": ["codename"]}
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document))

    code, out, _ = cli("show-policy", "tenant-a")
    assert code == 0 and "no active policy" in out and "platform default" in out

    code, out, _ = cli("set-policy", "tenant-a", str(path), "--by", "alice")
    assert code == 0 and "policy version 1 is now active for tenant tenant-a" in out
    code, out, _ = cli("set-policy", "tenant-a", str(path))
    assert "policy version 2" in out

    code, out, _ = cli("show-policy", "tenant-a")
    assert code == 0 and re.search(r"version 2 by admin-cli", out)
    shown = json.loads(out[out.index("{"):])
    assert shown["allowed_kbs"] == ["legal"] and shown["max_tool_calls"] == 2 and shown["blocked_terms"] == ["codename"]
    assert shown["max_tokens_per_request"] == 100_000  # defaults are filled in and stored

    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        cur.execute("SELECT version, active, created_by FROM policies ORDER BY version")
        assert cur.fetchall() == [(1, False, "alice"), (2, True, "admin-cli")]
    conn.close()
    assert cli("show-policy", "tenant-b")[1].startswith("tenant tenant-b has no active policy")  # other tenant untouched


@pytest.mark.parametrize("content, message", [
    ('{"allowed_kbs": "legal"}', "invalid policy document"),
    ('{"max_tool_calls": 999}', "invalid policy document"),
    ('{"allowed_kbs": ["legal"], "typo_field": 1}', "invalid policy document"),
    ("{not json", "cannot read policy file"),
    ("[1, 2]", "invalid policy document"),
])
def test_set_policy_rejects_an_invalid_file_and_changes_nothing(cli, tmp_path, database_url, content, message):
    path = tmp_path / "bad.json"
    path.write_text(content)
    code, out, err = cli("set-policy", "tenant-a", str(path))
    assert code == 2 and message in err and out == ""
    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM policies")
        assert cur.fetchone() == (0,)
    conn.close()


def test_set_policy_for_an_unknown_tenant_or_missing_file(cli, tmp_path):
    path = tmp_path / "ok.json"
    path.write_text("{}")
    code, _, err = cli("set-policy", "nobody", str(path))
    assert code == 2 and "unknown tenant 'nobody'" in err
    code, _, err = cli("set-policy", "tenant-a", str(tmp_path / "missing.json"))
    assert code == 2 and "cannot read policy file" in err

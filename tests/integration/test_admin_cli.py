"""The admin CLI: create tenant, principal, key; revoke; the secret is printed once (requirement 9)."""
import re
from uuid import UUID

import psycopg2
import pytest

from core.identity.keys import hash_secret, parse_key
from core.identity.store import authenticate_api_key
from scripts.admin.identity import main


def run(dsn, capsys, *args):
    code = main(["--dsn", dsn, *args])
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def cli(database_url, clean_state, capsys):
    return lambda *args: run(database_url, capsys, *args)


async def test_full_lifecycle_secret_shown_once_and_only_the_hash_stored(cli, database_url, db_pool):
    code, out, _ = cli("create-tenant", "acme", "--name", "Acme Ltd")
    assert code == 0 and "tenant acme created" in out
    tenant_id = UUID(re.search(r"id=([0-9a-f-]{36})", out).group(1))

    code, out, _ = cli("create-kb", "acme", "legal", "--description", "Law")
    assert code == 0

    code, out, _ = cli("create-principal", "acme", "service", "ingest-bot")
    principal_id = re.search(r"id=([0-9a-f-]{36})", out).group(1)

    code, out, _ = cli("create-key", principal_id, "--scopes", "query", "kb:read")
    assert code == 0
    token = re.search(r"KEY \(shown once, store it now\): (\S+)", out).group(1)
    prefix, secret = parse_key(token)
    assert f"prefix={prefix}" in out and "scopes=kb:read,query" in out
    assert out.count(secret) == 1  # printed exactly once

    # the database holds the hash, not the secret
    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        cur.execute("SELECT secret_hash, scopes, tenant_id FROM api_keys WHERE prefix = %s", (prefix,))
        stored_hash, scopes, key_tenant = cur.fetchone()
        cur.execute("SELECT api_keys::text FROM api_keys WHERE prefix = %s", (prefix,))
        whole_row_text = cur.fetchone()[0]
    conn.close()
    assert stored_hash == hash_secret(secret)
    assert sorted(scopes) == ["kb:read", "query"]
    assert UUID(str(key_tenant)) == tenant_id
    assert secret not in whole_row_text and token not in whole_row_text

    # list-keys never prints the secret or the hash
    code, out, _ = cli("list-keys", "--tenant", "acme")
    assert prefix in out and "acme/ingest-bot" in out and "active" in out
    assert secret not in out and stored_hash not in out

    # the key works, then revoke refuses it
    principal = await authenticate_api_key(db_pool, token)
    assert principal is not None and principal.tenant_id == tenant_id
    code, out, _ = cli("revoke-key", prefix)
    assert code == 0 and f"key {prefix} revoked" in out
    assert await authenticate_api_key(db_pool, token) is None
    code, out, _ = cli("list-keys")
    assert "revoked" in out and secret not in out


def test_revoking_an_unknown_or_already_revoked_key_fails_with_exit_code_1(cli):
    cli("create-tenant", "acme")
    code, _, err = cli("revoke-key", "nope1234")
    assert code == 1 and "no active key" in err


def test_bad_arguments_are_refused_and_nothing_is_created(cli, database_url):
    assert cli("create-tenant", "bad slug!")[0] == 2
    assert cli("create-principal", "ghost", "service", "x")[0] == 2  # unknown tenant
    for argv in (["create-principal", "ghost", "robot", "x"],  # kind not in user/service/agent
                 ["create-key", "00000000-0000-0000-0000-000000000000", "--scopes", "root"]):  # unknown scope
        with pytest.raises(SystemExit):
            main(["--dsn", database_url, *argv])
    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        for table in ("tenants", "principals", "api_keys"):
            cur.execute(f"SELECT count(*) FROM {table}")
            assert cur.fetchone() == (0,), table
    conn.close()


def test_creating_a_key_for_an_unknown_principal_is_refused(cli):
    code, _, err = cli("create-key", "00000000-0000-0000-0000-000000000000", "--scopes", "query")
    assert code == 2 and "unknown principal" in err


def test_create_tenant_seeds_a_default_kb_unless_told_not_to(cli, database_url):
    cli("create-tenant", "with-kb")
    cli("create-tenant", "no-kb", "--no-default-kb")
    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        cur.execute("SELECT t.slug, count(k.id) FROM tenants t LEFT JOIN knowledge_bases k ON k.tenant_id = t.id "
                    "GROUP BY t.slug ORDER BY t.slug")
        assert cur.fetchall() == [("no-kb", 0), ("with-kb", 1)]
    conn.close()

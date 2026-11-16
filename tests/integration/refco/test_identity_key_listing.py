"""Key listing and rotation use tenant context and retain unrelated credentials.

Only throwaway Postgres is needed; these fixtures never clean shared Valkey.
"""
import json
from uuid import uuid4

import pytest

from core.identity import admin
from scripts.showcase import personas


@pytest.fixture
def key_tenants(database_url):
    tenants = []
    for _ in range(2):
        slug = "key-review-" + uuid4().hex[:12]
        with admin.admin_connection(database_url) as conn:
            admin.create_tenant(conn, slug, default_kb=False, deploy_shape="multi_tenant")
            principal = admin.create_principal(conn, slug, "service", "key-client")
            key = admin.create_key(conn, principal, ["query"])
        tenants.append((slug, key.prefix))
    return tenants


@pytest.mark.parametrize("index", [0, 1])
def test_list_keys_sets_tenant_on_fresh_owner_connection(database_url, key_tenants, index):
    """admin.* runs as the owner role (module contract). list_keys must set its own tenant context."""
    slug, prefix = key_tenants[index]
    with admin.admin_connection(database_url) as conn:
        # list_keys is the first operation on this fresh connection: no context left by an earlier call.
        rows = admin.list_keys(conn, tenant_slug=slug)
        assert {row["prefix"] for row in rows} == {prefix}
        assert {row["tenant"] for row in rows} == {slug}
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('app.tenant_id', true), (SELECT id::text FROM tenants WHERE slug = %s)", (slug,))
            context, tenant_id = cur.fetchone()
            assert context == tenant_id


@pytest.mark.parametrize("lost_state", ["", "all", "manifest"], ids=["saved-state", "lost-state", "lost-manifest"])
def test_persona_rotation_preserves_foreign_key(database_url, key_tenants, tmp_path, monkeypatch, capsys, lost_state):
    slug, _ = key_tenants[0]
    state = tmp_path / "private"
    monkeypatch.setenv("MIGRATION_DATABASE_URL", database_url)
    monkeypatch.delenv("SHOWCASE_FIXTURE_KEY", raising=False)
    args = ["--tenant", slug, "--state-dir", str(state)]
    assert personas.main(args) == 0
    old = json.loads((state / "manifest.json").read_text())["personas"]["consumer"]["key_prefix"]
    consumer_name = next(p["name"] for p in personas.load_personas() if p["id"] == "consumer")
    with admin.admin_connection(database_url) as conn:
        principal = next(p["id"] for p in admin.list_principals(conn, slug) if p["name"] == consumer_name)
        foreign_prefix = admin.create_key(conn, principal, ["query"]).prefix
    if lost_state:
        if lost_state == "all":
            (state / "keys.env").unlink()
        (state / "manifest.json").unlink()
    capsys.readouterr()
    assert personas.main([*args, "--replace", "consumer"]) == 0
    output = capsys.readouterr().out
    with admin.admin_connection(database_url) as conn:
        rows = {row["prefix"]: row for row in admin.list_keys(conn, slug, principal_id=principal)}
    assert rows[foreign_prefix]["revoked_at"] is None
    assert (rows[old]["revoked_at"] is None) == bool(lost_state)
    manifest = json.loads((state / "manifest.json").read_text())
    new = manifest["personas"]["consumer"]["key_prefix"]
    assert new not in {old, foreign_prefix}
    count = 2 if lost_state else 1
    assert f"WARN consumer: {count} other active key(s) left untouched" in output
    assert foreign_prefix in output
    # Avoid printing plaintext even if this regression fails.
    leaked = any(line.partition("=")[2] in output for line in (state / "keys.env").read_text().splitlines())
    assert not leaked

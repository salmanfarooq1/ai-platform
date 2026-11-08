"""Online and offline receipt verification across v1 and v2 decision rows."""
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

from core.identity.admin import admin_connection, create_key
from tests import harness
from tests.integration.test_migration_record_v2 import _seed_v1_chain

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_receipt_v2_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


@pytest.mark.asyncio
async def test_mixed_chain_receipts_verify_offline(blank_db, monkeypatch, tmp_path):
    import psycopg2

    harness.require_redis()
    harness.migrate(blank_db, "0010")
    tenant_id, principal_id, old_ids = _seed_v1_chain(blank_db)
    with admin_connection(blank_db) as conn:
        key = create_key(conn, principal_id, ["audit:read"])
    harness.migrate(blank_db)

    import api.main
    import core.database.pool
    from adapters.redis_cache import RedisCache

    app_settings = api.main.settings.model_copy(update={"deploy_shape": "multi_tenant"})
    monkeypatch.setattr(api.main, "settings", app_settings)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", harness.app_url(blank_db))
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 2)
    application = api.main.create_app(adapter_overrides={
        "cache": RedisCache(harness.REDIS_URL, app_settings.embedding_dim),
    })
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     headers={"Authorization": f"Bearer {key.token}"}) as client:
            legacy_response = await client.get(f"/v1/receipts/{old_ids[0]}")
            assert legacy_response.status_code == 200, legacy_response.text
            legacy = legacy_response.json()
            assert legacy["decision"]["record_version"] == 1

            conn = psycopg2.connect(blank_db)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM gateway_decisions WHERE tenant_id = %s AND record_version = 2 "
                        "ORDER BY chain_position DESC LIMIT 1", (str(tenant_id),),
                    )
                    v2_id = cur.fetchone()[0]
            finally:
                conn.close()
            v2_response = await client.get(f"/v1/receipts/{v2_id}")
            assert v2_response.status_code == 200, v2_response.text
            current = v2_response.json()
            assert current["decision"]["record_version"] == 2
            keys_response = await client.get("/v1/receipts/keys")
            assert keys_response.status_code == 200
            public_keys = keys_response.json()

    key_file = tmp_path / "keys.json"
    key_file.write_text(json.dumps(public_keys), encoding="utf-8")
    for index, receipt in enumerate((legacy, current)):
        receipt_file = tmp_path / f"receipt-{index}.json"
        receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
        command = [sys.executable, str(ROOT / "scripts/verify/receipt.py"), "receipt", str(receipt_file),
                   "--keys", str(key_file)]
        verified = subprocess.run(command, text=True, capture_output=True, check=False)
        assert verified.returncode == 0, verified.stdout + verified.stderr
        receipt["decision"]["outcome"] = "deny" if receipt["decision"]["outcome"] == "allow" else "allow"
        receipt_file.write_text(json.dumps(receipt), encoding="utf-8")
        tampered = subprocess.run(command, text=True, capture_output=True, check=False)
        assert tampered.returncode != 0, tampered.stdout + tampered.stderr


@pytest.mark.asyncio
async def test_api_shows_version_and_extensions(blank_db, monkeypatch):
    harness.require_redis()
    harness.migrate(blank_db, "0010")
    tenant_id, principal_id, old_ids = _seed_v1_chain(blank_db)
    with admin_connection(blank_db) as conn:
        key = create_key(conn, principal_id, ["audit:read"])
    harness.migrate(blank_db)

    import api.main
    import core.database.pool
    from adapters.redis_cache import RedisCache

    configured = api.main.settings.model_copy(update={"deploy_shape": "multi_tenant"})
    monkeypatch.setattr(api.main, "settings", configured)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", harness.app_url(blank_db))
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 2)
    app = api.main.create_app(adapter_overrides={"cache": RedisCache(harness.REDIS_URL, configured.embedding_dim)})
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                     headers={"Authorization": f"Bearer {key.token}"}) as client:
            page = await client.get("/v1/decisions")
            assert page.status_code == 200, page.text
            newest = page.json()["items"][0]["id"]
            new_detail = await client.get(f"/v1/decisions/{newest}")
            old_detail = await client.get(f"/v1/decisions/{old_ids[0]}")
    assert new_detail.status_code == 200 and new_detail.json()["record_version"] == 2
    assert new_detail.json()["extensions"] == {}
    assert old_detail.status_code == 200 and old_detail.json()["record_version"] == 1
    assert old_detail.json()["extensions"] == {}

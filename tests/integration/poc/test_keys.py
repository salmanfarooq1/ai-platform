"""WP2 real database/API and worker checkpoint signatures across restart."""
import base64
import importlib.util
import json
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from core.identity.admin import admin_connection, create_key
from core.settings import Settings
from evidence.receipts import keyring_from_settings, verify_checkpoints
from tests.trust_helpers import run_purges, seed_chain


@pytest.mark.asyncio
async def test_api_worker_share_key_across_restart(tmp_path, monkeypatch, db_pool, owner_pool, tenant_a, database_url, app_database_url, fake_llm, fake_embeddings):
    from scripts.poc_lib.keys import ensure_stack_secrets

    files = ensure_stack_secrets(tmp_path, "keytest")
    monkeypatch.setenv("RECEIPT_SIGNING_KEY_FILE", str(files.key_file))
    monkeypatch.delenv("RECEIPT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", app_database_url)
    monkeypatch.setenv("EMBEDDED_WORKERS", "0")
    # The API and independent worker both use their production settings/keyring path.
    import api.main
    import core.database.pool
    from core.settings import get_settings
    from tests import harness

    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 4)
    monkeypatch.setenv("REDIS_URL", harness.REDIS_URL)
    with admin_connection(database_url) as conn:
        audit = create_key(conn, UUID(tenant_a.principal_id), ["audit:read"])

    await seed_chain(owner_pool, tenant_a.id, [200, 2])
    saved = []
    ids = []
    public_keys = tmp_path / "trusted-public-keys.json"
    try:
        for _ in range(2):
            get_settings.cache_clear()
            monkeypatch.setattr(api.main, "settings", get_settings())
            app = create_app(adapter_overrides={"llm": fake_llm, "embeddings": fake_embeddings, "chat": fake_llm})
            async with app.router.lifespan_context(app):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    decision_id = await owner_pool.fetchval("SELECT id FROM gateway_decisions WHERE tenant_id=$1 ORDER BY chain_position DESC LIMIT 1", UUID(tenant_a.id))
                    receipt = await client.get(f"/v1/receipts/{decision_id}", headers={"Authorization": f"Bearer {audit.token}"})
                    assert receipt.status_code == 200, receipt.text
                    saved.append(receipt.json())
                    ids.append(receipt.json()["key_id"])
                    if not public_keys.exists():
                        exported = await client.get("/v1/receipts/keys", headers={"Authorization": f"Bearer {audit.token}"})
                        assert exported.status_code == 200
                        public_keys.write_text(json.dumps(exported.json()))
            worker_ring = keyring_from_settings(Settings())
            await run_purges(db_pool, keyring=worker_ring)
            checkpoints = await owner_pool.fetch("SELECT position,row_hash,reason,signature,key_id FROM chain_checkpoints WHERE tenant_id=$1", UUID(tenant_a.id))
            assert verify_checkpoints(tenant_a.id, checkpoints, worker_ring.public_map()).ok
            assert {cp["key_id"] for cp in checkpoints if cp["reason"] == "purge"} == {ids[-1]}
        assert ids == [files.public_identity()["key_id"]] * 2
        spec = importlib.util.spec_from_file_location("wp2_offline", Path(__file__).resolve().parents[3] / "scripts/verify/receipt.py")
        offline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(offline)
        trusted = {key["key_id"]: base64.b64decode(key["public_key"]) for key in json.loads(public_keys.read_text())}
        receipts_file = tmp_path / "saved-receipts.json"
        receipts_file.write_text(json.dumps(saved))
        # The standalone verifier reads saved artifacts and needs no private key or server.
        for receipt in json.loads(receipts_file.read_text()):
            assert all(ok for _, ok, _ in offline.verify_receipt(receipt, trusted))
    finally:
        get_settings.cache_clear()

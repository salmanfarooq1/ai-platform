"""Boot each configured edition against the real local services and fake models."""
import os
from uuid import UUID

import httpx
import pytest
from asgi_lifespan import LifespanManager

from core.modules import EDITIONS, edition_for
from tests import harness

pytestmark = pytest.mark.edition_smoke


async def test_edition_smoke(monkeypatch, database_url, app_database_url, clean_state, tenant_a, fake_llm,
                            fake_embeddings, tmp_path):
    import api.main
    import core.database.pool
    from adapters.local_object_store import LocalObjectStore
    from adapters.redis_cache import RedisCache

    enabled_value = os.environ.get("ENABLED_MODULES", "gateway")
    enabled = frozenset(part.strip() for part in enabled_value.split(",") if part.strip())
    edition = edition_for(enabled)
    assert edition in EDITIONS, f"ENABLED_MODULES={enabled_value!r} is not a named edition"

    configured = api.main.settings.model_copy(update={
        "enabled_modules": enabled_value,
        "deploy_shape": "multi_tenant",
    })
    monkeypatch.setattr(api.main, "settings", configured)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 4)
    application = api.main.create_app(adapter_overrides={
        "llm": fake_llm,
        "chat": fake_llm,
        "embeddings": fake_embeddings,
        "cache": RedisCache(harness.REDIS_URL, configured.embedding_dim),
        "objects": LocalObjectStore(tmp_path),
    })

    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/v1/health")
            assert health.status_code == 200, health.text

            modules = await client.get("/v1/system/modules", headers=tenant_a.headers("reader"))
            assert modules.status_code == 200, modules.text
            body = modules.json()
            assert body["edition"] == edition
            assert {item["name"] for item in body["modules"] if item["enabled"]} == enabled

            documents = await client.get(
                "/v1/documents?namespace=default", headers=tenant_a.headers("reader"),
            )
            assert documents.status_code == 200, documents.text
            import asyncpg

            owner = await asyncpg.connect(dsn=database_url, statement_cache_size=0)
            try:
                decision = await owner.fetchrow(
                    "SELECT outcome, record_version FROM gateway_decisions WHERE tenant_id = $1 "
                    "AND action = 'kb.read' ORDER BY created_at DESC LIMIT 1",
                    UUID(tenant_a.id),
                )
            finally:
                await owner.close()
            assert decision is not None and decision["outcome"] == "allow"
            assert decision["record_version"] == 2

            agent = await client.post(
                "/v1/agent/query", headers=tenant_a.headers("full"),
                json={"question": "What is in the default knowledge base?", "namespace": "default"},
            )
            if "agents" not in enabled:
                assert agent.status_code == 404, agent.text
                assert agent.json()["error"]["code"] == "module_disabled"
            else:
                assert agent.status_code in (200, 202), agent.text

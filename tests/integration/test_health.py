import httpx
import pytest
from asgi_lifespan import LifespanManager

from tests.fakes import make_fake_catalog
from tests.harness import REDIS_URL

pytestmark = pytest.mark.integration


async def test_health_makes_no_inference(database_url, app_database_url, clean_state, fake_embeddings, fake_llm, monkeypatch):
    import api.main
    import core.database.pool
    from adapters.redis_cache import RedisCache

    configured = api.main.settings.model_copy(update={"deploy_shape": "multi_tenant"})
    monkeypatch.setattr(api.main, "settings", configured)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 2)
    app = api.main.create_app(adapter_overrides={
        "cache": RedisCache(REDIS_URL, configured.embedding_dim), "embeddings": fake_embeddings,
        "llm": fake_llm, "chat": fake_llm, "model_catalog": make_fake_catalog(configured),
    })
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            plain = await client.get("/health")
            versioned = await client.get("/v1/health")
    assert plain.status_code == versioned.status_code == 200
    body = plain.json()
    assert set(body) == {"status", "db", "redis", "embedding", "version", "mode", "uptime_seconds", "stale_vectors"}
    assert body["stale_vectors"] is not None
    assert {key: value for key, value in versioned.json().items() if key != "uptime_seconds"} == {
        key: value for key, value in body.items() if key != "uptime_seconds"
    }
    assert fake_embeddings.calls == []
    assert fake_llm.calls == []

"""System metadata needs any recognized API scope, after identity verification."""
import httpx
import pytest
from asgi_lifespan import LifespanManager

from core.identity.admin import admin_connection, create_key

pytestmark = pytest.mark.integration


@pytest.fixture
async def metadata_client(database_url, app_database_url, tenant_a, monkeypatch):
    import api.main
    import core.database.pool
    from adapters.redis_cache import RedisCache
    from tests.harness import REDIS_URL

    configured = api.main.settings.model_copy(update={"deploy_shape": "multi_tenant", "enabled_modules": "gateway"})
    monkeypatch.setattr(api.main, "settings", configured)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 2)
    app = api.main.create_app(adapter_overrides={"cache": RedisCache(REDIS_URL, configured.embedding_dim)})
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.parametrize("scope", ["kb:read", "kb:write", "query", "agent", "audit:read", "admin"])
async def test_each_single_scope_key_reads_metadata(metadata_client, database_url, tenant_a, scope):
    with admin_connection(database_url) as conn:
        key = create_key(conn, tenant_a.principal_id, [scope])
    response = await metadata_client.get("/v1/system/modules", headers={"Authorization": f"Bearer {key.token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"deploy_shape", "edition", "modules"} <= body.keys()
    assert all({"name", "label", "pillar", "description", "enabled", "nav_group", "always_on"} <= item.keys()
               for item in body["modules"])


async def test_no_credential_is_401_and_unknown_scope_is_403(metadata_client, database_url, tenant_a):
    assert (await metadata_client.get("/v1/system/modules")).status_code == 401
    with admin_connection(database_url) as conn:
        key = create_key(conn, tenant_a.principal_id, ["query"])
        with conn.cursor() as cursor:
            cursor.execute("UPDATE api_keys SET scopes = '{}' WHERE prefix = %s", (key.prefix,))
    response = await metadata_client.get("/v1/system/modules", headers={"Authorization": f"Bearer {key.token}"})
    assert response.status_code == 403

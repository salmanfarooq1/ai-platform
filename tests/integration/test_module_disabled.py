"""Jobs belonging to disabled modules remain outside the worker's claim set."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager

from api.module_routes import DISABLED_AGENT_ROUTES
from core.database import jobs
from core.database.tenant import tenant_connection
from core.identity.admin import admin_connection, create_key
from core.identity.models import Scope
from core.identity.run_tokens import issue_run_token
from core.settings import Settings
from gateway import build_boundary
from tests.db_fixtures import principal_of
from tests.harness import REDIS_URL
from workers.context import build_handlers
from workers.loop import Worker
from workers.types import JobOutput

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def gateway_client(database_url, app_database_url, tenant_a, monkeypatch):
    import api.main
    import core.database.pool
    from adapters.redis_cache import RedisCache

    configured = api.main.settings.model_copy(update={"deploy_shape": "multi_tenant", "enabled_modules": "gateway"})
    monkeypatch.setattr(api.main, "settings", configured)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 2)
    app = api.main.create_app(adapter_overrides={"cache": RedisCache(REDIS_URL, configured.embedding_dim)})
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def _module_denies(owner_pool, tenant_id):
    return await owner_pool.fetchval(
        "SELECT count(*) FROM gateway_decisions WHERE tenant_id = $1 AND outcome = 'deny' "
        "AND stage = 'module' AND reason = 'module_disabled'", tenant_id,
    )


async def test_every_route_of_a_disabled_module_is_denied(gateway_client, db_pool, owner_pool, database_url, tenant_a):
    agent = principal_of(tenant_a, ("agent",))
    for spec in DISABLED_AGENT_ROUTES:
        run_id = uuid4()
        path = spec.path.replace("{execution_id}", str(run_id)).replace("{name}", "retrieve_chunks")
        if spec.run_bound:
            issued = await issue_run_token(db_pool, agent, run_id, build_boundary(agent, None).to_payload(), 60)
            token = issued.token
        else:
            scope = spec.scopes[0].value if isinstance(spec.scopes[0], Scope) else str(spec.scopes[0])
            with admin_connection(database_url) as conn:
                key = create_key(conn, tenant_a.principal_id, [scope])
            token = key.token
        before = await _module_denies(owner_pool, UUID(tenant_a.id))
        response = await gateway_client.request(
            spec.methods[0], "/v1" + path, headers={"Authorization": f"Bearer {token}"},
            json={"question": "test"} if path == "/agent/query" else None,
        )
        assert response.status_code == 404 and response.json()["error"]["code"] == "module_disabled", path
        assert await _module_denies(owner_pool, UUID(tenant_a.id)) == before + 1, path


async def test_deny_is_recorded(gateway_client, owner_pool, tenant_a):
    response = await gateway_client.post("/v1/agent/query", json={"question": "test"}, headers=tenant_a.headers("full"))
    assert response.status_code == 404 and response.json()["error"]["code"] == "module_disabled"
    row = await owner_pool.fetchrow(
        "SELECT action, outcome, stage, reason FROM gateway_decisions WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 1",
        UUID(tenant_a.id),
    )
    assert tuple(row) == ("agent.run", "deny", "module", "module_disabled")


async def test_missing_credential_or_scope_wins_over_module(gateway_client, owner_pool, database_url, tenant_a):
    before = await _module_denies(owner_pool, UUID(tenant_a.id))
    assert (await gateway_client.post("/v1/agent/query", json={"question": "test"})).status_code == 401
    with admin_connection(database_url) as conn:
        query_key = create_key(conn, tenant_a.principal_id, ["query"])
    response = await gateway_client.post(
        "/v1/agent/query", json={"question": "test"}, headers={"Authorization": f"Bearer {query_key.token}"},
    )
    assert response.status_code == 403
    assert await _module_denies(owner_pool, UUID(tenant_a.id)) == before


async def test_worker_does_not_claim_disabled_job_kinds(db_pool, tenant_a, monkeypatch):
    tenant_id = UUID(tenant_a.id)
    expired_lease = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with tenant_connection(db_pool, tenant_id) as conn:
        queued_agent, _ = await jobs.enqueue(conn, tenant_id, "agent_run", {"input": {}})
        expired_agent, _ = await jobs.enqueue(conn, tenant_id, "agent_run", {"input": {}})
        await conn.execute(
            "UPDATE jobs SET status = 'running', attempts = 1, locked_by = 'expired-worker', "
            "lease_until = $2 WHERE id = $1",
            expired_agent.id, expired_lease,
        )
        ingest, _ = await jobs.enqueue(conn, tenant_id, "ingest", {"namespace": "legal"})

    async def ingest_handler(_job, _ctx):
        return JobOutput(result={"ok": True})

    monkeypatch.setattr("workers.context._make_ingest_handler", lambda _adapters: ingest_handler)
    settings = Settings(_env_file=None, enabled_modules="gateway", job_poll_interval_seconds=0.02)
    adapters = SimpleNamespace(events=None, knowledge=object(), embeddings=object(), objects=object())
    keyring = SimpleNamespace(sign=lambda _text: ("signature", "key"))
    handlers = build_handlers(
        adapters, db_pool, object(), settings=settings, keyring=keyring,
    )
    worker = Worker(db_pool, handlers, name="gateway-only", poll_interval=0.02)
    task = asyncio.create_task(worker.run())
    try:
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            async with tenant_connection(db_pool, tenant_id) as conn:
                ingest_row = await jobs.get(conn, ingest.id)
            if ingest_row is not None and ingest_row.status == "succeeded":
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("the always-on ingest job did not finish")
            await asyncio.sleep(0.02)
    finally:
        worker.stop()
        await asyncio.wait_for(task, 10)

    async with tenant_connection(db_pool, tenant_id) as conn:
        queued_after = await jobs.get(conn, queued_agent.id)
        expired_after = await jobs.get(conn, expired_agent.id)
    assert (queued_after.status, queued_after.attempts, queued_after.lease_until) == ("queued", 0, None)
    assert (expired_after.status, expired_after.attempts, expired_after.lease_until) == (
        "running", 1, expired_lease,
    )

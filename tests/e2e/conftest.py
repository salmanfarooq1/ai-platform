"""
tests/e2e/conftest.py

Fixtures for end-to-end tests: the real FastAPI app, started with its real lifespan
(`asgi-lifespan`) and called over HTTP (`httpx.ASGITransport`). Postgres and Redis are
real, the LLM and embeddings are the fakes in tests/fakes.py. Tests skip, with a
reason, when Postgres or Redis is unreachable.
"""
import asyncio
import io
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from tests import harness


@pytest.fixture
def platform_config(monkeypatch, app_database_url, clean_state):
    """Point the app at the throwaway database and test Redis, and turn the cross-encoder off.

    The app connects as `gap_app` (NOSUPERUSER NOBYPASSRLS), never as the owner, so row-level
    security applies to everything it does.

    Each consumer module holds its own reference to the config dicts, so each is patched in place.
    """
    import api.agent.graph
    import api.agent.tools
    import api.mcp.tools
    import api.routers.search
    import core.database.pool

    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 4)
    for module in (api.routers.search, api.agent.tools, api.agent.graph, api.mcp.tools):
        monkeypatch.setitem(module.FEATURES, "reranker_enabled", False)
    return app_database_url


WORKERS = 1


def adapter_overrides(request) -> dict[str, Any]:
    """The adapters the test app is built with (through `adapters/registry.py`).

    Postgres is the real adapter on a throwaway database, and so is Redis (the test instance). The provider
    ports get the fakes the test asked for (`fake_llm`, `fake_embeddings`). A test that asks for none keeps the
    real LiteLLM adapters, which the network guard blocks: that is what the network-guard tests rely on.
    """
    from adapters.local_object_store import LocalObjectStore
    from adapters.redis_cache import RedisCache
    from config import EMBEDDING_DIM

    # Raw uploads go to a throwaway directory (Sprint 007), never into the repository's data/objects.
    overrides: dict[str, Any] = {
        "cache": RedisCache(harness.REDIS_URL, EMBEDDING_DIM),
        "objects": LocalObjectStore(request.getfixturevalue("tmp_path")),
    }
    if "fake_llm" in request.fixturenames:
        llm = request.getfixturevalue("fake_llm")
        overrides.update(llm=llm, chat=llm)
    if "fake_embeddings" in request.fixturenames:
        overrides["embeddings"] = request.getfixturevalue("fake_embeddings")
    return overrides


@pytest_asyncio.fixture
async def app(platform_config, request):
    """A fresh app instance with its real lifespan started."""
    from api.main import create_app
    from tests import jobs_helpers

    jobs_helpers.OWNER["dsn"] = request.getfixturevalue("database_url")  # to read what ingest jobs did
    # One embedded worker runs the jobs (ingestion, agent runs) in this process, on the app's own ports.
    application = create_app(adapter_overrides=adapter_overrides(request), embedded_workers=WORKERS)
    async with LifespanManager(application):
        yield application


@pytest_asyncio.fixture
async def redis_raw(app):
    """A plain Redis client on the test instance, to look at the keys the platform wrote (not the app's adapter)."""
    import redis.asyncio as aioredis

    client = aioredis.Redis.from_url(harness.REDIS_URL, decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def make_client(app):
    """Factory for HTTP clients on the app. `make_client(headers)` sends those headers on every request.

    raise_app_exceptions=False: an unhandled error must come back as a 500 response, as in production.
    """
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    clients: list[httpx.AsyncClient] = []

    def factory(headers: dict[str, str] | None = None) -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=transport, base_url="http://test", headers=headers or {})
        clients.append(c)
        return c

    yield factory
    for c in clients:
        await c.aclose()


@pytest_asyncio.fixture
async def client(make_client, tenant_a):
    """Authenticated as tenant A with its full-scope key."""
    return make_client(tenant_a.headers("full"))


@pytest_asyncio.fixture
async def client_b(make_client, tenant_b):
    """Authenticated as tenant B with its full-scope key."""
    return make_client(tenant_b.headers("full"))


@pytest_asyncio.fixture
async def anon_client(make_client):
    """No credentials."""
    return make_client()


@pytest_asyncio.fixture
async def pool(app, database_url):
    """Owner-role pool for verifying what the app wrote, across tenants. The app itself uses gap_app."""
    import asyncpg

    owner = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=2, statement_cache_size=0)
    try:
        yield owner
    finally:
        await owner.close()


@pytest.fixture
def json_logs():
    """Capture what the JSON formatter would write, as parsed objects."""
    import api.main  # noqa: F401 - importing the app module installs the logging setup
    from api.observability import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.INFO)

    def lines() -> list[dict[str, Any]]:
        import json

        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


async def eventually(check: Callable[[], Any], timeout: float = 5.0) -> Any:
    """Poll an async-or-sync check until it returns something truthy (fire-and-forget writes)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = check()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return result
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition was not met in time")
        await asyncio.sleep(0.05)

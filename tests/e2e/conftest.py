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
    import api.services.cache
    import core.database.pool

    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "pool_size", 4)
    monkeypatch.setitem(api.services.cache.CACHE_CONFIG, "url", harness.REDIS_URL)
    for module in (api.routers.search, api.agent.tools, api.agent.graph, api.mcp.tools):
        monkeypatch.setitem(module.FEATURES, "reranker_enabled", False)
    monkeypatch.setattr(api.services.cache, "_redis_pool", None)
    return app_database_url


@pytest_asyncio.fixture
async def app(platform_config):
    """A fresh app instance with its real lifespan started."""
    from api.main import create_app

    application = create_app()
    async with LifespanManager(application):
        yield application


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

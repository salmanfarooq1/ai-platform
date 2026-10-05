"""
tests/integration/conftest.py

Fixtures for integration tests: real Postgres (pgvector) and Redis, but fake LLM and
embeddings. `database_url`, `app_database_url`, `clean_state`, `tenants`, `fake_llm` and
`fake_embeddings` come from tests/db_fixtures.py.

`db_pool` connects as `gap_app` (NOSUPERUSER NOBYPASSRLS), the role the app uses, so row-level
security applies to everything done through it. `owner_pool` is the superuser, for verifying what
was written regardless of tenant. Never use it to perform the operation under test.
"""
import asyncpg
import pytest_asyncio
import redis.asyncio as aioredis
from pgvector.asyncpg import register_vector

from adapters.pg_knowledge import PgKnowledgeStore
from adapters.redis_cache import RedisCache
from tests import harness


@pytest_asyncio.fixture
async def db_pool(app_database_url, clean_state):
    pool = await asyncpg.create_pool(
        dsn=app_database_url, min_size=1, max_size=4, init=register_vector, statement_cache_size=0,
    )
    try:
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def owner_pool(database_url, clean_state):
    pool = await asyncpg.create_pool(
        dsn=database_url, min_size=1, max_size=2, init=register_vector, statement_cache_size=0,
    )
    try:
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def redis_client(clean_state):
    client = aioredis.Redis.from_url(harness.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def knowledge_store(db_pool):
    """The real Postgres knowledge store, as `gap_app` (row-level security applies)."""
    return PgKnowledgeStore(db_pool)


@pytest_asyncio.fixture
async def redis_cache(clean_state):
    """The real Redis cache adapter on the test instance."""
    from config import EMBEDDING_DIM

    cache = RedisCache(harness.REDIS_URL, EMBEDDING_DIM)
    try:
        yield cache
    finally:
        await cache.close()

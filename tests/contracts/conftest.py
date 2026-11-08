"""Real Postgres fixture for shared evidence-port contracts."""
import asyncpg
import pytest_asyncio
from pgvector.asyncpg import register_vector


@pytest_asyncio.fixture
async def db_pool(app_database_url, clean_state):
    pool = await asyncpg.create_pool(
        dsn=app_database_url, min_size=1, max_size=4, init=register_vector, statement_cache_size=0,
    )
    try:
        yield pool
    finally:
        await pool.close()

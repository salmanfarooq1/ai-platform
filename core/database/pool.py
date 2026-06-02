import asyncpg
from asyncpg import Pool
from pgvector.asyncpg import register_vector
from config import DATABASE_CONFIG

async def create_pool() -> Pool:
    '''
    Create and return an asyncpg connection pool with pgvector registered on every connection.

    Uses DATABASE_CONFIG["url"] (DSN string) so the pool connects to the correct
    database for the active MODE (local/demo/prod). Switching MODE changes the
    target database without touching this code.

    init=register_vector ensures every connection the pool creates understands
    pgvector custom types and can serialize Python lists into PostgreSQL vector columns.
    '''
    pool_size = DATABASE_CONFIG.get("pool_size", 20)

    pool = await asyncpg.create_pool(
        dsn = DATABASE_CONFIG["url"],
        min_size = max(1, pool_size // 4),   # keep 25% of max alive when idle
        max_size = pool_size,                # ceiling on simultaneous connections
        init = register_vector               # called on every new connection the pool creates
    )
    return pool
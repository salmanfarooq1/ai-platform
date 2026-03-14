import asyncpg
from pgvector.asyncpg import register_vector
from config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, MIN_POOL_SIZE, MAX_POOL_SIZE

async def create_pool():
    pool = await asyncpg.create_pool(
        host = POSTGRES_HOST,
        port = POSTGRES_PORT,
        database = POSTGRES_DB,
        user = POSTGRES_USER,
        password = POSTGRES_PASSWORD,
        min_size = MIN_POOL_SIZE,
        max_size = MAX_POOL_SIZE,
        init = register_vector
    )  
    return pool
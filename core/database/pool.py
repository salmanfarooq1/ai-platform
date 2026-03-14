import asyncpg
from asyncpg import Pool
from pgvector.asyncpg import register_vector
from config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, MIN_POOL_SIZE, MAX_POOL_SIZE

async def create_pool() -> Pool:
    '''
    Create and return an asyncpg connection pool with pgvector registered on every connection.

    Pooling effectively minimizes connection overhead which includes TCP handshake and postgres auth, it does that by reusing the same connections

    using init=register_vector, asyncpg understands the pgvector custom types, it also helps to serialize python lists into the PostgreSQL vector type, we pass it as init= so that every connection the pool ever creates gets registered automatically
    '''
    pool = await asyncpg.create_pool(
        host = POSTGRES_HOST,
        port = POSTGRES_PORT,
        database = POSTGRES_DB,
        user = POSTGRES_USER,
        password = POSTGRES_PASSWORD,
        min_size = MIN_POOL_SIZE,   # connections kept alive even when idle — avoids cold-start latency
        max_size = MAX_POOL_SIZE,   # ceiling on simultaneous connections — protects the DB from overload
        init = register_vector      # called on every new connection the pool creates
    )
    return pool
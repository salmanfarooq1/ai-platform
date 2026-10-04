"""Tenant-scoped database access. Every request-path query goes through `tenant_connection`.

It opens a transaction and sets `app.tenant_id` with `set_config(..., is_local => true)`, which is
`SET LOCAL` with a bound parameter. The setting disappears when the transaction ends, so a pooled
connection never carries one tenant's id into another request. Row-level security policies read it.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from asyncpg import Connection, Pool

# The pool type, for callers that must not import asyncpg directly (api/agent/tools.py, api/mcp/*: see the
# import-lint test). Data access goes through `tenant_connection`.
DbPool = Pool


@asynccontextmanager
async def tenant_connection(pool: Pool, tenant_id: UUID | str) -> AsyncIterator[Connection]:
    tenant = str(UUID(str(tenant_id)))  # rejects anything that is not a UUID
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            yield conn

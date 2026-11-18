"""One platform-wide advisory lock that keeps a backup and a decision purge apart.

A POC backup copies the database and the objects it points to. A purge deletes decision rows and signs a checkpoint.
If a purge ran in the middle of a capture, the dump and its manifest could describe a chain that no longer exists. So
capture takes this lock EXCLUSIVELY (one session-level lock on its own connection) and every purge batch takes it SHARED
inside its own transaction: purges never block each other, a purge waits while capture owns the lock, and capture waits
for a purge that is in flight. Ordinary writes and the per-tenant decision-chain locks do not use it.

Any code that will delete stored objects or decision rows must call `purge_guard` in the same transaction as the delete.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from asyncpg import Connection

BACKUP_LOCK_KEY = 0x504F434241434B  # "POCBACK"; one fixed bigint for the whole platform
PURGE_WAIT_SECONDS = 30.0  # a purge job waits at most this long for a capture, then is deferred (not failed) by the worker


class BackupLockTimeout(TimeoutError):
    """The backup lock could not be taken in time (a purge is in flight), or a purge could not get past a capture."""


def _millis(seconds: float) -> str:
    return f"{max(1, int(seconds * 1000))}ms"


async def purge_guard(conn: Connection, *, timeout: float = PURGE_WAIT_SECONDS) -> None:
    """Take the shared lock for the rest of the current transaction. Call it before planning, signing or deleting.

    `timeout` bounds only the wait for the lock: once it is held, the transaction's previous `lock_timeout` is put back, so
    the plan and batch statements that follow are not cut short by it."""
    previous = str(await conn.fetchval("SELECT current_setting('lock_timeout')"))
    await conn.execute("SELECT set_config('lock_timeout', $1, true)", _millis(timeout))
    try:
        await conn.execute("SELECT pg_advisory_xact_lock_shared($1)", BACKUP_LOCK_KEY)
    except asyncpg.LockNotAvailableError:
        raise BackupLockTimeout("a backup is capturing; the purge will retry") from None
    await conn.execute("SELECT set_config('lock_timeout', $1, true)", previous)


@asynccontextmanager
async def backup_guard(conn: Connection, *, timeout: float) -> AsyncIterator[None]:
    """Hold the exclusive lock on `conn` (a dedicated, non-pooled-in-use connection) until the block ends.

    Released on success, on any error and on cancellation. Waits up to `timeout` seconds for an in-flight purge."""
    await conn.execute("SELECT set_config('lock_timeout', $1, false)", _millis(timeout))
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", BACKUP_LOCK_KEY)
    except asyncpg.LockNotAvailableError:
        raise BackupLockTimeout("a purge is in flight; the backup could not take the lock in time") from None
    finally:
        await conn.execute("SELECT set_config('lock_timeout', '0', false)")
    try:
        yield
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", BACKUP_LOCK_KEY)

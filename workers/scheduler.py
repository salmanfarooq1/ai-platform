"""The retention scheduler: once a day per tenant, queue a `purge_decisions` job when it has expired records.

A worker calls `schedule_purges` every `RETENTION_SCHEDULE_INTERVAL_SECONDS` (0 turns it off). The narrow function
`retention_due_tenants` names the tenants that have at least one expired record. The job's idempotency key holds the
UTC date, so any number of workers, API processes and passes queue at most one job per tenant per day.
"""
import asyncio
import contextlib
import logging
from datetime import datetime, timezone

from core.database import jobs
from core.database.tenant import DbPool, tenant_connection

logger = logging.getLogger("workers.scheduler")


async def schedule_purges(pool: DbPool, default_days: int, *, max_attempts: int = 3) -> int:
    """Queue today's purge job for every tenant that has expired records. Returns how many jobs were created."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = await pool.fetch("SELECT due_tenant FROM retention_due_tenants($1)", default_days)
    created = 0
    for row in rows:
        tenant_id = row["due_tenant"]
        async with tenant_connection(pool, tenant_id) as conn:
            _, new = await jobs.enqueue(
                conn, tenant_id, jobs.KIND_PURGE, {}, idempotency_key=f"{jobs.KIND_PURGE}:{today}", max_attempts=max_attempts,
            )
        created += int(new)
    if created:
        logger.info("retention: queued %d purge job(s)", created)
    return created


async def run_scheduler(pool: DbPool, default_days: int, interval: float, stop: asyncio.Event) -> None:
    """Loop until `stop` is set. A failed pass is logged and tried again at the next interval."""
    while not stop.is_set():
        try:
            await schedule_purges(pool, default_days)
        except Exception:
            logger.error("retention scheduling failed", exc_info=True)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), interval)

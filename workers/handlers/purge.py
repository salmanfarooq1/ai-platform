"""The `purge_decisions` job: delete a tenant's expired decision records, in batches (Q7, ADR-0012).

One job is one tenant. Each batch runs `decisions_purge_batch` (migration 0009) under `tenant_connection` as the app
role. The function writes the chain checkpoint first and deletes in the same transaction, and this handler writes the
`platform.gateway.purge.v1` event to the outbox in that transaction too, so a batch is visible exactly when it
happened. The function refuses any tenant but the one the connection works as, and computes the cutoff itself.

Every batch first takes the shared backup lock (`core/database/locks.py`): a POC backup holds it exclusively while it
captures, so a purge never runs in the middle of a capture.

If a capture holds the lock longer than the wait, the job is DEFERRED (`DeferJob`): put back as `queued` for `DEFER_SECONDS`
later without using an attempt, so a long backup can never push a purge to `dead`. The lock wait bounds only the lock; the
plan and batch statements keep the connection's normal timeouts.

The job can run again without harm: a second run finds nothing expired and returns at once.
"""
import logging
from collections.abc import Callable

from core.database.jobs import JobRow
from core.database.locks import BackupLockTimeout, purge_guard
from core.database.tenant import tenant_connection
from evidence.receipts import checkpoint_text
from ports import DECISIONS_PURGED, CloudEvent, EventBus
from workers.types import DeferJob, Handler, JobContext, JobOutput

logger = logging.getLogger("workers.purge")

EVENT_SOURCE = "/gateway/retention"
DEFER_SECONDS = 60.0  # how long a purge that met a capturing backup waits before it tries again
_PLAN = "SELECT plan_position, plan_hash FROM decisions_purge_plan($1, $2, $3)"
_BATCH = (
    "SELECT purged, checkpoint_position, checkpoint_hash, retention_days FROM decisions_purge_batch($1, $2, $3, $4, $5, $6, $7)"
)
# Signs a checkpoint text with the receipt key: returns (signature, key_id).
Signer = Callable[[str], tuple[str, str]]


def purge_event(job: JobRow, purged: int, position: int | None, row_hash: str | None, days: int) -> CloudEvent:
    """Counts, a position and a hash: no decision content."""
    return CloudEvent(
        type=DECISIONS_PURGED, source=EVENT_SOURCE, subject=str(job.id), tenantid=str(job.tenant_id),
        data={
            "job_id": str(job.id), "purged": purged, "retention_days": days,
            "checkpoint_position": position, "checkpoint_hash": row_hash,
        },
    )


def make_purge_handler(events: EventBus | None, default_days: int, batch_size: int, signer: Signer) -> Handler:
    async def handle(job: JobRow, ctx: JobContext) -> JobOutput:
        total, batches = 0, 0
        while True:
            async with tenant_connection(ctx.pool, job.tenant_id) as conn:
                # A backup capture owns this lock exclusively; wait for it before planning, so the dump never sees a purge.
                try:
                    await purge_guard(conn)
                except BackupLockTimeout:
                    raise DeferJob("backup_in_progress", DEFER_SECONDS, "a backup is capturing; the purge runs after it") from None
                # Plan, sign, then purge: the function writes a checkpoint only if it is the one that was signed.
                plan = await conn.fetchrow(_PLAN, job.tenant_id, default_days, batch_size)
                position = hash_ = signature = key_id = None
                if plan is not None and plan["plan_position"] is not None:
                    position, hash_ = int(plan["plan_position"]), str(plan["plan_hash"])
                    signature, key_id = signer(checkpoint_text(job.tenant_id, position, hash_, "purge"))
                row = await conn.fetchrow(_BATCH, job.tenant_id, default_days, batch_size, position, hash_, signature, key_id)
                if row is None or row["purged"] == 0:
                    break
                if events is not None:  # same transaction as the checkpoint and the delete
                    await events.publish(
                        purge_event(job, row["purged"], row["checkpoint_position"], row["checkpoint_hash"], row["retention_days"]),
                        tx=conn,
                    )
            total += int(row["purged"])
            batches += 1
        logger.info("purge job %s: tenant=%s purged=%d batches=%d", job.id, job.tenant_id, total, batches)
        return JobOutput(result={"purged": total, "batches": batches})

    return handle

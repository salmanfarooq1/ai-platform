"""Fix round 1 (MEDIUM): a purge that cannot get past a long backup is deferred, never consumed into `dead`.

`DeferJob` is the general seam (any handler may raise it); the queue does not know about purges. A deferral puts the job
back as `queued` for a later time and does not count the attempt.
"""
import asyncio
import time
from uuid import UUID

import pytest

from core.database import jobs, locks
from core.database.tenant import tenant_connection
from tests.trust_helpers import KEYRING, seed_chain
from workers.handlers import purge
from workers.loop import Worker
from workers.scheduler import schedule_purges

pytestmark = pytest.mark.asyncio


async def _status(owner_pool, tenant: UUID, kind: str):
    return await owner_pool.fetchrow(
        "SELECT status, attempts, max_attempts, error_code, run_after > now() AS later FROM jobs WHERE tenant_id = $1 AND kind = $2",
        tenant, kind)


async def test_defer_puts_a_claimed_job_back_without_using_an_attempt(db_pool, owner_pool, tenant_a):
    tenant = UUID(tenant_a.id)
    async with tenant_connection(db_pool, tenant) as conn:
        job, _ = await jobs.enqueue(conn, tenant, "ingest", {}, idempotency_key="defer-1", max_attempts=2)
    for round_ in range(6):  # more rounds than max_attempts: it must never reach `dead`
        await owner_pool.execute("UPDATE jobs SET run_after = now() WHERE id = $1", job.id)
        claimed = await jobs.claim(db_pool, f"slot-{round_}", 30, ("ingest",))
        assert claimed is not None and claimed[0] == job.id
        async with tenant_connection(db_pool, tenant) as conn:
            assert await jobs.defer(conn, job.id, f"slot-{round_}", 60.0, "backup_in_progress", "a backup is capturing") == "queued"
        row = await owner_pool.fetchrow("SELECT status, attempts, error_code, run_after > now() AS later FROM jobs WHERE id = $1", job.id)
        assert (row["status"], row["attempts"], row["error_code"], row["later"]) == ("queued", 0, "backup_in_progress", True)


async def test_six_lock_timeouts_leave_the_purge_job_queued_not_dead(db_pool, owner_pool, tenant_a, monkeypatch):
    await seed_chain(owner_pool, tenant_a.id, [200, 150, 100, 95, 10, 5, 1])
    tenant = UUID(tenant_a.id)
    real_guard = purge.purge_guard
    timeouts = []

    async def short_guard(conn, *, timeout=0.15):
        try:
            await real_guard(conn, timeout=0.15)
        except locks.BackupLockTimeout:
            timeouts.append(time.monotonic())
            raise

    monkeypatch.setattr(purge, "purge_guard", short_guard)
    monkeypatch.setattr(purge, "DEFER_SECONDS", 0.05, raising=False)
    created = await schedule_purges(db_pool, 90, max_attempts=3)
    assert created >= 1
    worker = Worker(db_pool, {jobs.KIND_PURGE: purge.make_purge_handler(None, 90, 1000, KEYRING.sign)}, name="defer-test",
                    lease_seconds=30, poll_interval=0.02, beat_interval=0.1, backoff_base=0.0, shutdown_grace=0.3)
    async with owner_pool.acquire() as backup_conn:
        async with locks.backup_guard(backup_conn, timeout=5):  # a long backup owns the lock
            task = asyncio.create_task(worker.run(1))
            try:
                deadline = time.monotonic() + 60
                while len(timeouts) < 6:
                    assert time.monotonic() < deadline, f"only {len(timeouts)} lock timeouts"
                    await asyncio.sleep(0.05)
                row = await _status(owner_pool, tenant, jobs.KIND_PURGE)
                assert row["status"] in ("queued", "running"), dict(row)  # pending or rescheduled, never dead
                assert row["attempts"] <= 1, dict(row)  # the deferrals did not consume attempts (max_attempts is 3)
            finally:
                worker.stop()
                await asyncio.wait_for(task, 10)
        assert await owner_pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE tenant_id = $1", tenant) == 7
    row = await _status(owner_pool, tenant, jobs.KIND_PURGE)
    assert row["status"] != "dead"
    # The backup is over: the next run of the same job completes and purges.
    await owner_pool.execute("UPDATE jobs SET run_after = now() WHERE tenant_id = $1 AND kind = $2", tenant, jobs.KIND_PURGE)
    worker = Worker(db_pool, {jobs.KIND_PURGE: purge.make_purge_handler(None, 90, 1000, KEYRING.sign)}, name="defer-test-2",
                    lease_seconds=30, poll_interval=0.02, beat_interval=0.1, backoff_base=0.0, shutdown_grace=0.3)
    task = asyncio.create_task(worker.run(1))
    try:
        deadline = time.monotonic() + 30
        while (await _status(owner_pool, tenant, jobs.KIND_PURGE))["status"] != "succeeded":
            assert time.monotonic() < deadline, "the deferred purge never ran after the backup ended"
            await asyncio.sleep(0.05)
    finally:
        worker.stop()
        await asyncio.wait_for(task, 10)
    assert await owner_pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE tenant_id = $1", tenant) == 3


async def test_a_handler_raising_defer_job_is_deferred_by_the_queue(db_pool, owner_pool, tenant_a):
    from workers.types import DeferJob

    tenant = UUID(tenant_a.id)
    calls = []

    async def handler(job, ctx):
        calls.append(1)
        raise DeferJob("busy", 0.05, "try later")

    async with tenant_connection(db_pool, tenant) as conn:
        await jobs.enqueue(conn, tenant, "ingest", {}, idempotency_key="defer-2", max_attempts=2)
    worker = Worker(db_pool, {"ingest": handler}, name="defer-generic", lease_seconds=30, poll_interval=0.02,
                    beat_interval=0.1, backoff_base=0.0, shutdown_grace=0.3)
    task = asyncio.create_task(worker.run(1))
    try:
        deadline = time.monotonic() + 30
        while len(calls) < 5:
            assert time.monotonic() < deadline
            await asyncio.sleep(0.05)
    finally:
        worker.stop()
        await asyncio.wait_for(task, 10)
    row = await _status(owner_pool, tenant, "ingest")
    assert row["status"] in ("queued", "running") and row["attempts"] <= 1 and row["error_code"] == "busy"


async def test_each_deferral_is_counted_on_the_job_and_the_read_model_shows_it(db_pool, owner_pool, tenant_a):
    """015 WP3 fix-round review, LOW (a): the count survives on the row and is part of `JobRow`; the delay is at least 1 s."""
    tenant = UUID(tenant_a.id)
    async with tenant_connection(db_pool, tenant) as conn:
        job, _ = await jobs.enqueue(conn, tenant, "ingest", {}, idempotency_key="defer-count", max_attempts=2)
    assert job.deferrals == 0
    for round_ in range(1, 4):
        await owner_pool.execute("UPDATE jobs SET run_after = now() WHERE id = $1", job.id)
        assert (await jobs.claim(db_pool, f"slot-{round_}", 30, ("ingest",)))[0] == job.id
        async with tenant_connection(db_pool, tenant) as conn:
            assert await jobs.defer(conn, job.id, f"slot-{round_}", 0.0, "busy") == "queued"
        async with tenant_connection(db_pool, tenant) as conn:
            row = await jobs.get(conn, job.id)
        assert row.deferrals == round_
        waited = await owner_pool.fetchval("SELECT extract(epoch FROM run_after - now()) FROM jobs WHERE id = $1", job.id)
        assert 0.0 < waited <= 1.0  # a zero delay was clamped up to one second, not left at "now"
    # A real failure does not touch the count.
    await owner_pool.execute("UPDATE jobs SET run_after = now() WHERE id = $1", job.id)
    await jobs.claim(db_pool, "slot-fail", 30, ("ingest",))
    async with tenant_connection(db_pool, tenant) as conn:
        await jobs.fail(conn, job.id, "slot-fail", "boom", retry=True, backoff_base=0.0)
        assert (await jobs.get(conn, job.id)).deferrals == 3

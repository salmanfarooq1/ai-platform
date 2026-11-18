"""Fix round 1 (purge must not starve behind a long backup): the lock wait bounds only the lock, and a timeout defers."""
import asyncpg
import pytest

from core.database import locks
from workers.types import DeferJob


class FakeConn:
    """Records statements. `current` is the transaction's lock_timeout; `blocked` makes the lock statement time out."""

    def __init__(self, current="0", blocked=False):
        self.current, self.blocked, self.log = current, blocked, []

    async def fetchval(self, sql, *args):
        self.log.append(("fetchval", sql, args))
        return self.current

    async def execute(self, sql, *args):
        self.log.append(("execute", sql, args))
        if "set_config" in sql and "lock_timeout" in sql:
            self.current = args[0]
        if "pg_advisory_xact_lock_shared" in sql and self.blocked:
            raise asyncpg.LockNotAvailableError("canceling statement due to lock timeout")


@pytest.mark.asyncio
async def test_purge_guard_restores_the_previous_lock_timeout_after_the_lock_is_taken():
    conn = FakeConn(current="7s")
    await locks.purge_guard(conn, timeout=30)
    order = [(kind, args) for kind, sql, args in conn.log if "lock_timeout" in sql or "xact_lock" in sql or "current_setting" in sql]
    sets = [args[0] for kind, args in order if kind == "execute" and args and isinstance(args[0], str)]
    assert sets[0] == "30000ms" and sets[-1] == "7s"  # bounded for the lock only, then back to what it was
    assert conn.current == "7s", "the plan and batch statements must not run under the 30 s lock bound"
    lock_index = next(i for i, (_, sql, _a) in enumerate(conn.log) if "pg_advisory_xact_lock_shared" in sql)
    restore_index = max(i for i, (_, sql, a) in enumerate(conn.log) if "set_config" in sql and a == ("7s",))
    assert restore_index > lock_index


@pytest.mark.asyncio
async def test_purge_guard_timeout_raises_backup_lock_timeout():
    with pytest.raises(locks.BackupLockTimeout):
        await locks.purge_guard(FakeConn(blocked=True), timeout=0.1)


def test_defer_job_is_a_general_seam_not_a_purge_special_case():
    error = DeferJob("backup_in_progress", 30.0, "a backup is capturing")
    assert (error.code, error.delay_seconds, error.detail) == ("backup_in_progress", 30.0, "a backup is capturing")
    assert not issubclass(DeferJob, TimeoutError)


# --- 015 WP3 fix-round review, LOW (a): a deferral is bounded, finite and counted ---------------------------------------

@pytest.mark.parametrize("delay", [float("nan"), float("inf"), float("-inf"), "soon", None])
def test_defer_job_rejects_a_non_finite_or_non_numeric_delay(delay):
    with pytest.raises(ValueError, match="delay"):
        DeferJob("backup_in_progress", delay)


@pytest.mark.parametrize("delay,expected", [(0, 1.0), (0.0, 1.0), (-5, 1.0), (0.05, 1.0), (1, 1.0), (1.5, 1.5), (60, 60.0)])
def test_defer_job_clamps_the_delay_to_at_least_one_second(delay, expected):
    error = DeferJob("backup_in_progress", delay)
    assert error.delay_seconds == expected and isinstance(error.delay_seconds, float)


class RecordingConn:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "UPDATE 1"


@pytest.mark.asyncio
@pytest.mark.parametrize("delay,expected", [(0.0, 1.0), (-3.0, 1.0), (0.2, 1.0), (45.0, 45.0)])
async def test_queue_defer_clamps_and_counts_the_deferral(delay, expected):
    from uuid import uuid4

    from core.database import jobs

    conn = RecordingConn()
    assert await jobs.defer(conn, uuid4(), "slot", delay, "busy") == "queued"
    sql, args = conn.calls[0]
    assert "deferrals = deferrals + 1" in sql  # the count is kept on the job row, in the same statement
    assert args[-1] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [float("nan"), float("inf")])
async def test_queue_defer_refuses_a_non_finite_delay_before_any_statement(delay):
    from uuid import uuid4

    from core.database import jobs

    conn = RecordingConn()
    with pytest.raises(ValueError, match="delay"):
        await jobs.defer(conn, uuid4(), "slot", delay, "busy")
    assert conn.calls == []


def test_job_row_carries_the_deferral_count_with_zero_as_default():
    import dataclasses

    from core.database import jobs

    field = {f.name: f for f in dataclasses.fields(jobs.JobRow)}["deferrals"]
    assert field.default == 0
    assert "deferrals" in jobs._COLUMNS.split(", ") or "deferrals" in jobs._COLUMNS


@pytest.mark.asyncio
async def test_worker_logs_the_deferral_count(caplog, monkeypatch):
    import logging
    from datetime import datetime, timezone
    from uuid import uuid4

    from core.database import jobs
    from workers import loop

    now = datetime.now(timezone.utc)
    row = jobs.JobRow(
        id=uuid4(), tenant_id=uuid4(), kind="purge", status="queued", payload={}, idempotency_key=None, attempts=0,
        max_attempts=3, run_after=now, lease_until=None, locked_by=None, progress_done=0, progress_total=0,
        error_code="backup_in_progress", error_detail=None, resource=None, execution_id=None, result=None,
        cancel_requested=False, created_at=now, updated_at=now, started_at=None, finished_at=None, principal_id=None,
        namespace=None, deferrals=4)

    class Conn:
        pass

    class Ctx:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *exc):
            return False

    async def fake_defer(conn, job_id, worker_id, delay, code, detail=None):
        return "queued"

    async def fake_get(conn, job_id):
        return row

    monkeypatch.setattr(loop, "tenant_connection", lambda pool, tenant: Ctx())
    monkeypatch.setattr(loop.jobs, "defer", fake_defer)
    monkeypatch.setattr(loop.jobs, "get", fake_get)
    worker = loop.Worker.__new__(loop.Worker)
    worker._pool = object()
    with caplog.at_level(logging.INFO, logger="workers.loop"):
        await worker._finish_deferred("slot", row, DeferJob("backup_in_progress", 60.0))
    message = " ".join(r.getMessage() for r in caplog.records)
    assert "deferral 4" in message and "backup_in_progress" in message

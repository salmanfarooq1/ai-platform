"""Sprint 007 A2: the job queue on real Postgres, as the app role. Claim races, retries, dead letters,
idempotency, row-level security, a crashed worker and a worker that is told to stop."""
import asyncio
import os
import signal
import sys
from uuid import UUID, uuid4

import asyncpg
import pytest

from core.database import jobs
from core.database.tenant import tenant_connection
from workers.loop import Worker
from workers.types import JobOutput, PermanentJobError

pytestmark = pytest.mark.asyncio


def make_worker(pool, handler, name="w", **kw):
    options = dict(lease_seconds=30, poll_interval=0.02, beat_interval=0.1, backoff_base=0.0, shutdown_grace=0.3)
    options.update(kw)
    return Worker(pool, {"ingest": handler}, name=name, **options)


async def add(pool, tenant, payload=None, **kw):
    async with tenant_connection(pool, UUID(tenant.id)) as conn:
        job, _ = await jobs.enqueue(conn, UUID(tenant.id), "ingest", payload or {"namespace": "legal"}, **kw)
    return job


async def read(pool, tenant, job_id):
    async with tenant_connection(pool, UUID(tenant.id)) as conn:
        return await jobs.get(conn, job_id)


async def until(check, timeout=15.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        value = await check()
        if value:
            return value
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.03)


async def run_until(worker, check, concurrency=1):
    task = asyncio.create_task(worker.run(concurrency))
    try:
        return await until(check)
    finally:
        worker.stop()
        await asyncio.wait_for(task, 10)


async def test_two_claims_at_once_never_return_the_same_job(db_pool, tenant_a):
    await add(db_pool, tenant_a)
    got = await asyncio.gather(*[jobs.claim(db_pool, f"w{i}", 30) for i in range(8)])
    assert len([g for g in got if g is not None]) == 1


async def test_two_workers_running_together_run_every_job_exactly_once(db_pool, tenant_a):
    ids = [(await add(db_pool, tenant_a, {"namespace": "legal", "n": i})).id for i in range(20)]
    ran: list[UUID] = []
    who: set[str] = set()

    async def handler(job, ctx):
        ran.append(job.id)
        who.add(ctx.worker_id.split("/")[0])
        await asyncio.sleep(0.02)

    w1, w2 = make_worker(db_pool, handler, "one"), make_worker(db_pool, handler, "two")
    t1, t2 = asyncio.create_task(w1.run(2)), asyncio.create_task(w2.run(2))

    async def all_done():
        rows = [await read(db_pool, tenant_a, i) for i in ids]
        return all(r.status == "succeeded" for r in rows)

    try:
        await until(all_done)
    finally:
        w1.stop(), w2.stop()
        await asyncio.gather(t1, t2)
    assert sorted(ran) == sorted(ids)  # no job ran twice, none was missed
    assert who == {"one", "two"}  # both workers took part
    assert [(await read(db_pool, tenant_a, i)).attempts for i in ids] == [1] * 20


async def test_a_failed_attempt_is_retried_and_then_succeeds(db_pool, tenant_a):
    job = await add(db_pool, tenant_a)
    attempts = []

    async def handler(j, ctx):
        attempts.append(j.attempts)
        if len(attempts) == 1:
            raise RuntimeError("transient provider error")
        return JobOutput(result={"ok": True})

    async def done():
        row = await read(db_pool, tenant_a, job.id)
        return row if row.status == "succeeded" else None

    row = await run_until(make_worker(db_pool, handler), done)
    assert attempts == [1, 2] and row.attempts == 2 and row.result == {"ok": True} and row.error_code is None


async def test_a_retry_waits_for_its_backoff(db_pool, tenant_a):
    job = await add(db_pool, tenant_a)

    async def boom(j, ctx):
        raise RuntimeError("x")

    async def queued_later():
        row = await read(db_pool, tenant_a, job.id)
        return row if row.status == "queued" and row.attempts == 1 else None

    row = await run_until(make_worker(db_pool, boom, backoff_base=30.0), queued_later)
    assert row.error_code == "internal_error" and (row.run_after - row.updated_at).total_seconds() > 20
    assert await jobs.claim(db_pool, "other", 30) is None  # not claimable before run_after


async def test_a_job_that_keeps_failing_is_dead_after_max_attempts(db_pool, tenant_a):
    job = await add(db_pool, tenant_a, max_attempts=3)
    runs = []

    async def boom(j, ctx):
        runs.append(1)
        raise RuntimeError("password=hunter2")

    async def dead():
        row = await read(db_pool, tenant_a, job.id)
        return row if row.status == "dead" else None

    row = await run_until(make_worker(db_pool, boom), dead)
    assert len(runs) == 3 and row.attempts == 3 and row.error_code == "internal_error"
    assert "hunter2" not in (row.error_detail or "")  # only the exception type is kept
    assert await jobs.claim(db_pool, "other", 30) is None  # dead jobs are never claimed again


async def test_a_permanent_error_fails_at_once_without_a_retry(db_pool, tenant_a):
    job = await add(db_pool, tenant_a)

    async def handler(j, ctx):
        raise PermanentJobError("unsupported_file")

    async def failed():
        row = await read(db_pool, tenant_a, job.id)
        return row if row.status == "failed" else None

    row = await run_until(make_worker(db_pool, handler), failed)
    assert row.attempts == 1 and row.error_code == "unsupported_file"


async def test_the_same_idempotency_key_returns_the_same_job(db_pool, tenant_a, tenant_b):
    a1 = await add(db_pool, tenant_a, idempotency_key="upload-1")
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        again, created = await jobs.enqueue(conn, UUID(tenant_a.id), "ingest", {"namespace": "legal"}, idempotency_key="upload-1")
    assert again.id == a1.id and created is False
    raced = await asyncio.gather(*[add(db_pool, tenant_a, idempotency_key="upload-2") for _ in range(6)])
    assert len({j.id for j in raced}) == 1  # six callers at once, one job
    b1 = await add(db_pool, tenant_b, idempotency_key="upload-1")  # the key is per tenant
    assert b1.id != a1.id
    no_key = {(await add(db_pool, tenant_a)).id for _ in range(2)}
    assert len(no_key) == 2  # no key: no dedupe


async def test_rls_as_the_app_role_hides_other_tenants_jobs(db_pool, tenant_a, tenant_b):
    mine, theirs = await add(db_pool, tenant_a), await add(db_pool, tenant_b)
    assert await read(db_pool, tenant_a, theirs.id) is None
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        assert [j.id for j in await jobs.list_jobs(conn)] == [mine.id]
        with pytest.raises(asyncpg.PostgresError):  # cannot write a row for another tenant
            await jobs.enqueue(conn, UUID(tenant_b.id), "ingest", {})
    async with db_pool.acquire() as conn:  # no tenant set: nothing is visible
        assert await conn.fetchval("SELECT count(*) FROM jobs") == 0
        assert await conn.execute("UPDATE jobs SET status = 'dead'") == "UPDATE 0"
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        assert await jobs.get_by_execution(conn, uuid4()) is None


async def test_the_claim_function_returns_only_an_id_and_a_tenant(db_pool, tenant_a):
    job = await add(db_pool, tenant_a)
    claimed = await jobs.claim(db_pool, "w", 30)
    assert claimed == (job.id, UUID(tenant_a.id))
    async with db_pool.acquire() as conn:
        record = await conn.fetchrow("SELECT * FROM jobs_claim('w', 30)")
        assert record is None or list(record.keys()) == ["claimed_id", "claimed_tenant"]
        assert await conn.fetchval("SELECT has_table_privilege('gap_app', 'jobs', 'DELETE')") is False


async def test_the_app_role_may_not_delete_jobs_and_a_payload_text_is_bounded(db_pool, tenant_a):
    await add(db_pool, tenant_a)
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM jobs")
    with pytest.raises(jobs.PayloadTooLarge):
        await add(db_pool, tenant_a, {"text": "x" * 5000})


async def test_a_killed_worker_leaves_its_job_to_be_claimed_again_after_the_lease(db_pool, tenant_a, database_url, app_database_url):
    job = await add(db_pool, tenant_a)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "tests.support.crash_worker", app_database_url,
        stdout=asyncio.subprocess.PIPE, env={**os.environ, "PYTHONPATH": "."},
    )
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), 30)
        assert line.decode().strip() == f"RUNNING {job.id}"
        proc.send_signal(signal.SIGKILL)  # a crash: no cleanup, no release
        await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()
    stuck = await read(db_pool, tenant_a, job.id)
    assert stuck.status == "running" and stuck.attempts == 1  # still held by a dead worker
    assert await jobs.claim(db_pool, "early", 30) is None  # the lease has not run out yet

    ran = []

    async def handler(j, ctx):
        ran.append(j.attempts)

    async def done():
        row = await read(db_pool, tenant_a, job.id)
        return row if row.status == "succeeded" else None

    row = await run_until(make_worker(db_pool, handler, "rescuer"), done)
    assert ran == [2] and row.attempts == 2  # re-claimed once the 2 second lease expired


async def test_a_job_that_loses_its_last_attempt_to_a_crash_is_dead_not_rerun(db_pool, tenant_a, owner_pool):
    job = await add(db_pool, tenant_a, max_attempts=1)
    assert await jobs.claim(db_pool, "gone", 30) is not None
    await owner_pool.execute("UPDATE jobs SET lease_until = NOW() - interval '1 second' WHERE id = $1", job.id)
    assert await jobs.claim(db_pool, "next", 30) is None
    row = await read(db_pool, tenant_a, job.id)
    assert row.status == "dead" and row.error_code == "lease_expired"


async def test_a_worker_that_lost_its_lease_stops_and_writes_nothing(db_pool, tenant_a, owner_pool):
    job = await add(db_pool, tenant_a)
    started = asyncio.Event()

    async def handler(j, ctx):
        started.set()
        await asyncio.sleep(30)

    worker = make_worker(db_pool, handler, "slow")
    task = asyncio.create_task(worker.run(1))
    await asyncio.wait_for(started.wait(), 10)
    await owner_pool.execute("UPDATE jobs SET locked_by = 'someone-else' WHERE id = $1", job.id)

    async def stopped():
        return worker.completed == 1

    await until(stopped)
    worker.stop()
    await asyncio.wait_for(task, 10)
    row = await read(db_pool, tenant_a, job.id)
    assert row.status == "running" and row.locked_by == "someone-else"  # the new owner's job, untouched


async def test_shutdown_lets_a_short_job_finish_and_releases_a_long_one(db_pool, tenant_a):
    quick, slow = await add(db_pool, tenant_a), None
    started = asyncio.Event()

    async def handler(j, ctx):
        if j.id == quick.id:
            await asyncio.sleep(0.2)
            return
        started.set()
        await asyncio.sleep(60)

    worker = make_worker(db_pool, handler, "stopper", shutdown_grace=0.3)
    task = asyncio.create_task(worker.run(1))

    async def quick_done():
        return (await read(db_pool, tenant_a, quick.id)).status == "succeeded"

    await until(quick_done)
    slow = await add(db_pool, tenant_a)
    await asyncio.wait_for(started.wait(), 10)
    worker.stop()
    await asyncio.wait_for(task, 10)
    row = await read(db_pool, tenant_a, slow.id)
    assert row.status == "queued" and row.locked_by is None and row.attempts == 0  # released, the attempt not counted


async def test_stop_requests_end_a_queued_job_at_once_and_a_running_job_at_its_next_beat(db_pool, tenant_a):
    queued = await add(db_pool, tenant_a)
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        row = await jobs.request_cancel(conn, queued.id)
    assert (row.status, row.error_code) == ("failed", "stopped")

    running = await add(db_pool, tenant_a)
    started = asyncio.Event()

    async def handler(j, ctx):
        started.set()
        await asyncio.sleep(60)

    worker = make_worker(db_pool, handler, "canceller")
    task = asyncio.create_task(worker.run(1))
    await asyncio.wait_for(started.wait(), 10)
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        await jobs.request_cancel(conn, running.id)

    async def ended():
        r = await read(db_pool, tenant_a, running.id)
        return r if r.status == "failed" else None

    try:
        r = await until(ended)
    finally:
        worker.stop()
        await asyncio.wait_for(task, 10)
    assert r.error_code == "stopped"


async def test_progress_is_recorded_while_the_job_runs(db_pool, tenant_a):
    job = await add(db_pool, tenant_a)
    seen = asyncio.Event()

    async def handler(j, ctx):
        await ctx.progress(3, 10)
        seen.set()
        await asyncio.sleep(0.5)
        await ctx.progress(10, 10)

    task = asyncio.create_task(make_worker(db_pool, handler).run(1))
    try:
        await asyncio.wait_for(seen.wait(), 10)
        row = await until(lambda: _progress(db_pool, tenant_a, job.id, 3))
        assert (row.progress_done, row.progress_total) == (3, 10)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _progress(pool, tenant, job_id, done):
    row = await read(pool, tenant, job_id)
    return row if row.progress_done == done else None


# ------------------------------------------------------------------ QA fixes

async def test_l5_a_claimed_job_that_cannot_be_read_is_given_back_at_once(db_pool, tenant_a, monkeypatch):
    job = await add(db_pool, tenant_a)
    real_get, calls = jobs.get, []

    async def flaky(conn, job_id):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("read failed")
        return await real_get(conn, job_id)

    monkeypatch.setattr(jobs, "get", flaky)
    ran = []

    async def handler(j, ctx):
        ran.append(j.attempts)

    async def done():
        async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
            row = await conn.fetchrow("SELECT status, attempts FROM jobs WHERE id = $1", job.id)
        return row if row["status"] == "succeeded" else None

    # the lease is 30 s: without the release the job would sit `running` until it ended
    row = await run_until(make_worker(db_pool, handler, lease_seconds=30), done)
    assert ran == [1] and row["attempts"] == 1  # released without counting, claimed again at once


async def test_l1_the_payload_cap_follows_the_questions_own_limit(db_pool, tenant_a):
    from adapters.job_runtime import JobAgentRuntime
    from ports import RunSpec

    def context(limit):
        return {"principal": {"id": tenant_a.principal_id}, "boundary": {"max_query_length": limit}}

    class Ctx:
        execution_id = None

    question = "\U0001F600" * 3000  # 3000 characters, 12000 bytes: within a max_query_length of 3000
    spec = RunSpec(kind="agent.query", input={"question": question, "namespace": "legal"}, tenant_id=UUID(tenant_a.id), context=Ctx())
    allowed = JobAgentRuntime(db_pool, serialize_context=lambda c: context(3000))
    handle = await allowed.start(spec)
    assert (await allowed.status(handle.run_id)).kind == "agent.query"
    refused = JobAgentRuntime(db_pool, serialize_context=lambda c: context(1000))  # a longer text than the limit allows
    with pytest.raises(jobs.PayloadTooLarge):
        await refused.start(spec)
    # without a context the old 4096 byte cap still holds
    with pytest.raises(jobs.PayloadTooLarge):
        await JobAgentRuntime(db_pool).start(RunSpec(kind="agent.query", input={"question": "x" * 5000}, tenant_id=UUID(tenant_a.id)))


async def test_m3_usage_is_booked_at_most_once_per_execution_id(db_pool, tenant_a, owner_pool):
    from api.agent.response import book_agent_usage
    from gateway import GatewayRuntime
    from tests.gateway_helpers import FakeRedis

    cache = FakeRedis()
    runtime = GatewayRuntime(pool=db_pool, cache=cache)
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_cost": 0.0, "model": "m", "namespace": "legal", "routing_decision": "agent"}
    run_a, run_b = uuid4(), uuid4()
    first = await book_agent_usage(db_pool, runtime, UUID(tenant_a.id), "req-1", usage, run_a)
    again = await book_agent_usage(db_pool, runtime, UUID(tenant_a.id), "req-1", usage, run_a)  # a re-claimed run
    other = await book_agent_usage(db_pool, runtime, UUID(tenant_a.id), "req-2", usage, run_b)
    assert first and other and again == {}
    assert await owner_pool.fetchval("SELECT count(*) FROM usage_log WHERE request_id = 'req-1'") == 1
    assert sum(cache.store.values()) == 30  # 15 tokens for each of the two runs, not 45

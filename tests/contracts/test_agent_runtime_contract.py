"""One contract for every `AgentRuntime`: start, status, wait, stop (also during a tool call) and cleanup.

Two runtimes pass it: the in-process one and the queued one (Sprint 007), where a run is a job that a worker
executes (the worker is a real `Worker` on real Postgres). OpenShell (009) must pass it too. A runner stands in for
the agent: it can finish at once, fail, or sit inside a tool call. A run's output is JSON, because the queued runtime
stores it with the job.
"""
import asyncio
from uuid import UUID, uuid4

import asyncpg
import psycopg2
import pytest
import pytest_asyncio

from adapters.inprocess_runtime import InProcessAgentRuntime
from adapters.job_runtime import JobAgentRuntime
from ports import RunNotFound, RunSpec, RunState
from workers.handlers.agent_run import make_agent_run_handler
from workers.loop import Worker

TENANT = uuid4()


class Controls:
    def __init__(self):
        self.in_tool = asyncio.Event()
        self.release = asyncio.Event()
        self.tool_was_cancelled = False
        self.finished = []


@pytest.fixture
def controls():
    return Controls()


@pytest_asyncio.fixture(params=["in-process", "job-queue"])
async def runtime(request, controls):
    async def runner(spec: RunSpec):
        mode = spec.input.get("mode", "quick")
        if mode == "fail":
            raise RuntimeError("the agent crashed")
        if mode == "tool":  # the run is inside a tool call until it is released or stopped
            controls.in_tool.set()
            try:
                await controls.release.wait()
            except asyncio.CancelledError:
                controls.tool_was_cancelled = True
                raise
        controls.finished.append(spec.execution_id)
        return {"answer": spec.input.get("question", ""), "execution_id": str(spec.execution_id)}

    if request.param == "in-process":
        yield InProcessAgentRuntime(runner)
        return
    request.getfixturevalue("clean_state")  # truncates, so the tenant row is added after it
    owner = psycopg2.connect(request.getfixturevalue("database_url"))
    owner.autocommit = True
    with owner.cursor() as cur:
        cur.execute("INSERT INTO tenants (id, slug, name) VALUES (%s, %s, 'Contract') ON CONFLICT DO NOTHING", (str(TENANT), f"rt-{str(TENANT)[:8]}"))
    owner.close()
    pool = await asyncpg.create_pool(dsn=request.getfixturevalue("app_database_url"), min_size=1, max_size=6, statement_cache_size=0)
    handler = make_agent_run_handler(InProcessAgentRuntime(runner), None)  # type: ignore[arg-type]
    worker = Worker(pool, {"agent_run": handler}, name="contract", poll_interval=0.02, beat_interval=0.05, shutdown_grace=1.0)
    task = asyncio.create_task(worker.run(4))
    try:
        yield JobAgentRuntime(pool, poll_interval=0.02, stop_wait_seconds=5.0)
    finally:
        worker.stop()
        await asyncio.wait_for(task, 10)
        await pool.close()


def spec(**input):
    return RunSpec(kind="agent.query", input=input or {"question": "q"}, tenant_id=TENANT)


async def test_a_run_starts_with_an_execution_id_and_finishes_with_its_output(runtime):
    handle = await runtime.start(spec(question="what is the deadline?"))
    assert isinstance(handle.execution_id, UUID) and handle.run_id
    result = await runtime.wait(handle.run_id)
    assert result.status.state is RunState.SUCCEEDED and result.status.error is None
    assert result.output == {"answer": "what is the deadline?", "execution_id": str(handle.execution_id)}
    assert (result.status.run_id, result.status.execution_id) == (handle.run_id, handle.execution_id)
    assert (result.status.tenant_id, result.status.kind) == (TENANT, "agent.query")
    assert result.status.finished_at is not None and result.status.finished_at >= result.status.started_at


async def test_every_run_gets_its_own_execution_id_and_a_caller_may_choose_it(runtime):
    a, b = await runtime.start(spec()), await runtime.start(spec())
    assert a.execution_id != b.execution_id
    chosen = uuid4()
    handle = await runtime.start(RunSpec(kind="agent.query", input={}, tenant_id=TENANT, execution_id=chosen))
    assert handle.execution_id == chosen
    assert (await runtime.wait(handle.run_id)).status.execution_id == chosen


async def test_status_is_running_until_the_run_ends(runtime, controls):
    handle = await runtime.start(spec(mode="tool"))
    await asyncio.wait_for(controls.in_tool.wait(), 2)
    status = await runtime.status(handle.run_id)
    assert status.state is RunState.RUNNING and status.finished_at is None
    controls.release.set()
    assert (await runtime.wait(handle.run_id)).status.state is RunState.SUCCEEDED
    assert (await runtime.status(handle.run_id)).state is RunState.SUCCEEDED


async def test_a_failing_run_is_a_failed_result_with_the_error_not_an_exception(runtime):
    handle = await runtime.start(spec(mode="fail"))
    result = await runtime.wait(handle.run_id)
    assert result.status.state is RunState.FAILED
    # The in-process runtime keeps the text in memory. The queued one stores a code only (QA L2): text can hold secrets.
    assert result.status.error == ("the agent crashed" if isinstance(runtime, InProcessAgentRuntime) else "agent_run_failed")
    assert result.output is None


async def test_stop_during_a_tool_call_cancels_the_tool_and_ends_the_run_stopped(runtime, controls):
    handle = await runtime.start(spec(mode="tool"))
    await asyncio.wait_for(controls.in_tool.wait(), 2)  # the run is inside the tool call right now
    status = await runtime.stop(handle.run_id)
    assert status.state is RunState.STOPPED and status.finished_at is not None
    assert controls.tool_was_cancelled is True
    assert controls.finished == []  # the run never reached its end
    result = await runtime.wait(handle.run_id)
    assert result.status.state is RunState.STOPPED and result.output is None


async def test_stopping_a_finished_run_changes_nothing(runtime):
    handle = await runtime.start(spec())
    done = await runtime.wait(handle.run_id)
    assert (await runtime.stop(handle.run_id)) == done.status
    assert (await runtime.stop(handle.run_id)).state is RunState.SUCCEEDED


async def test_stopping_twice_is_fine(runtime, controls):
    handle = await runtime.start(spec(mode="tool"))
    await asyncio.wait_for(controls.in_tool.wait(), 2)
    first, second = await runtime.stop(handle.run_id), await runtime.stop(handle.run_id)
    assert first.state is second.state is RunState.STOPPED


async def test_a_run_stopped_before_it_took_a_step_is_stopped_too(runtime, controls):
    handle = await runtime.start(spec(mode="tool"))
    status = await runtime.stop(handle.run_id)  # no await in between: the task has not run yet
    assert status.state is RunState.STOPPED
    assert (await runtime.wait(handle.run_id)).status.state is RunState.STOPPED


async def test_cleanup_stops_a_running_run_and_keeps_its_terminal_status_readable(runtime, controls):
    handle = await runtime.start(spec(mode="tool"))
    await asyncio.wait_for(controls.in_tool.wait(), 2)
    await runtime.cleanup(handle.run_id)
    assert controls.tool_was_cancelled is True
    assert (await runtime.status(handle.run_id)).state is RunState.STOPPED
    await runtime.cleanup(handle.run_id)  # idempotent


async def test_cleanup_releases_the_output_of_a_finished_run(runtime):
    handle = await runtime.start(spec(question="keep me?"))
    assert (await runtime.wait(handle.run_id)).output["answer"] == "keep me?"
    await runtime.cleanup(handle.run_id)
    after = await runtime.wait(handle.run_id)
    assert after.output is None and after.status.state is RunState.SUCCEEDED


async def test_an_unknown_run_raises_run_not_found(runtime):
    for call in (runtime.status, runtime.wait, runtime.stop, runtime.cleanup):
        with pytest.raises(RunNotFound):
            await call("no-such-run")


async def test_concurrent_runs_are_independent(runtime, controls):
    slow = await runtime.start(spec(mode="tool"))
    fast = await runtime.start(spec(question="fast"))
    assert (await runtime.wait(fast.run_id)).output["answer"] == "fast"
    assert (await runtime.status(slow.run_id)).state is RunState.RUNNING
    await runtime.stop(slow.run_id)
    assert (await runtime.status(fast.run_id)).state is RunState.SUCCEEDED


async def test_the_history_is_bounded_and_only_finished_runs_are_dropped(controls):
    async def runner(spec):
        if spec.input.get("mode") == "tool":
            await controls.release.wait()
        return None

    runtime = InProcessAgentRuntime(runner, max_tracked=2)
    running = await runtime.start(spec(mode="tool"))
    finished = []
    for _ in range(3):
        handle = await runtime.start(spec())
        await runtime.wait(handle.run_id)
        finished.append(handle)
    await runtime.start(spec())
    assert (await runtime.status(running.run_id)).state is RunState.RUNNING  # never dropped while running
    with pytest.raises(RunNotFound):
        await runtime.status(finished[0].run_id)  # the oldest finished one made room
    controls.release.set()
    await runtime.wait(running.run_id)


async def test_a_runtime_without_a_runner_refuses_to_start():
    with pytest.raises(RuntimeError):
        await InProcessAgentRuntime().start(spec())

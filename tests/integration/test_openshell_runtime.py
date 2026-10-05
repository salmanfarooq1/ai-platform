"""The OpenShell runtime's own behaviour on real Postgres, with a fake sandbox: limits, failure codes, the event log, the run
token's life and stopping a run. (The AgentRuntime contract is in tests/contracts; the whole path through the app is in
tests/e2e/test_sandbox_runs.py.)"""
import asyncio
import json
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from adapters import openshell_runtime
from adapters.openshell_runtime import OpenShellAgentRuntime, SandboxConfig
from adapters.sandbox_events import MAX_EVENTS_PER_RUN
from gateway import build_context
from ports import EgressRule, RunSpec, RunState, SandboxEventKind, SandboxLimits, SandboxOutput
from tests.db_fixtures import principal_of
from tests.fake_sandbox import FakeSandboxDriver, SandboxProcess
from tests.gateway_helpers import FakeRedis, make_runtime

pytestmark = pytest.mark.integration

WALL = 2


@pytest_asyncio.fixture
async def pool(app_database_url, clean_state, tenant_a):
    pool = await asyncpg.create_pool(dsn=app_database_url, min_size=1, max_size=4, statement_cache_size=0)
    try:
        yield pool
    finally:
        await pool.close()


def config(**changes):
    base = dict(
        gateway_url="http://gateway.test:8000", egress=EgressRule("gateway.test", 8000), limits=SandboxLimits("500m", "256Mi", WALL),
        work_dir="/sandbox/work", read_only=("/usr", "/lib"), network_binaries=("/usr/bin/python3*",), entry_source="pass",
    )
    return SandboxConfig(**{**base, **changes})


def make(pool, program, **changes):
    driver = FakeSandboxDriver(program)
    return OpenShellAgentRuntime(driver, pool, config(**changes)), driver


async def done(program_output: dict | None = None, code: int = 0):
    async def program(proc: SandboxProcess) -> int:
        if program_output is not None:
            proc.stdout(json.dumps({"result": program_output}) + "\n")
        return code

    return program


async def events(owner_pool, execution_id):
    rows = await owner_pool.fetch("SELECT kind, detail FROM sandbox_events WHERE execution_id = $1 ORDER BY at, seq", execution_id)
    return [(r["kind"], json.loads(r["detail"])) for r in rows]


def spec(tenant, **fields):
    return RunSpec(kind="agent.query", input={"question": "q"}, tenant_id=UUID(tenant.id), **fields)


async def with_context(pool, tenant):
    return await build_context(make_runtime(FakeRedis(), pool=pool), principal_of(tenant, ("agent",)), "req", "a" * 32)


async def test_a_run_is_launched_with_the_policy_the_blueprint_asks_for(pool, tenant_a):
    runtime, driver = make(pool, await done({"ok": 1}))
    handle = await runtime.start(spec(tenant_a, context=await with_context(pool, tenant_a)))
    result = await runtime.wait(handle.run_id)
    assert result.status.state is RunState.SUCCEEDED and result.output == {"ok": 1}
    [launch] = driver.launches
    assert launch.policy.egress == (EgressRule("gateway.test", 8000),)  # the only network route
    assert launch.policy.work_dir == "/sandbox/work" and launch.policy.read_only == ("/usr", "/lib")
    assert launch.policy.network_binaries == ("/usr/bin/python3*",)
    assert launch.policy.limits == SandboxLimits("500m", "256Mi", WALL)
    assert set(launch.env) == {"GATEWAY_URL", "EXECUTION_ID", "WORK_DIR", "RUN_TOKEN"}
    assert launch.command[0] == "python3" and launch.command[-1] == "answer"
    assert json.loads(launch.stdin) == {"input": {"question": "q"}}


async def test_a_run_without_an_enforcement_context_gets_no_token_so_it_cannot_call_the_gateway(pool, owner_pool, tenant_a):
    runtime, driver = make(pool, await done({"ok": 1}))
    handle = await runtime.start(spec(tenant_a))
    assert (await runtime.wait(handle.run_id)).status.state is RunState.SUCCEEDED
    assert "RUN_TOKEN" not in driver.launches[0].env
    assert await owner_pool.fetchval("SELECT count(*) FROM run_tokens") == 0


async def test_the_token_lives_for_the_wall_limit_and_a_minute_and_ends_with_the_run(pool, owner_pool, tenant_a):
    runtime, _ = make(pool, await done({"ok": 1}))
    handle = await runtime.start(spec(tenant_a, context=await with_context(pool, tenant_a)))
    await runtime.wait(handle.run_id)
    [row] = await owner_pool.fetch("SELECT EXTRACT(EPOCH FROM expires_at - created_at) AS ttl, revoked_at, execution_id FROM run_tokens")
    assert WALL + 59 <= float(row["ttl"]) <= WALL + 61 and row["revoked_at"] is not None and row["execution_id"] == handle.execution_id


async def test_the_wall_clock_limit_stops_the_run_and_says_so(pool, owner_pool, tenant_a):
    cancelled = []

    async def forever(proc: SandboxProcess) -> int:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return 0

    runtime, driver = make(pool, forever)
    handle = await runtime.start(spec(tenant_a, context=await with_context(pool, tenant_a)))
    result = await asyncio.wait_for(runtime.wait(handle.run_id), 10)
    assert result.status.state is RunState.FAILED and result.status.error == "wall_time_exceeded" and result.output is None
    assert cancelled == [True] and driver.destroyed == [handle.run_id] and driver.live == set()
    kinds = await events(owner_pool, handle.execution_id)
    assert [k for k, _ in kinds] == ["start", "limit_hit", "exit"]
    assert kinds[1][1] == {"limit": "wall_seconds", "value": WALL} and kinds[2][1] == {"reason": "wall_time_exceeded"}
    assert await owner_pool.fetchval("SELECT revoked_at IS NOT NULL FROM run_tokens")


async def test_a_process_killed_with_exit_137_is_recorded_as_a_limit_hit_marked_with_its_source(pool, owner_pool, tenant_a):
    async def killed(proc: SandboxProcess) -> int:
        return 137  # what OpenShell's memory limit did to a process on a live gateway: no event, exit status 137

    runtime, _ = make(pool, killed)
    handle = await runtime.start(spec(tenant_a))
    assert (await runtime.wait(handle.run_id)).status.error == "sandbox_exit_137"
    rows = await events(owner_pool, handle.execution_id)
    assert [k for k, _ in rows] == ["start", "limit_hit", "exit"]
    assert rows[1][1]["source"] == "exit_code" and rows[1][1]["limit"] == "memory" and rows[1][1]["value"] == "256Mi"


async def test_a_limit_the_sandbox_reports_is_recorded_as_a_limit_event(pool, owner_pool, tenant_a):
    async def oom(proc: SandboxProcess) -> int:
        proc.hit_limit("memory", "256Mi")
        return 137

    runtime, _ = make(pool, oom)
    handle = await runtime.start(spec(tenant_a))
    result = await runtime.wait(handle.run_id)
    assert result.status.error == "sandbox_exit_137"
    assert [k for k, _ in await events(owner_pool, handle.execution_id)] == ["start", "limit_hit", "exit"]


@pytest.mark.parametrize("print_, code, error", [
    ("not json at all\n", 0, "bad_output"),
    ('{"no_result_key": 1}\n', 0, "bad_output"),
    ('[1, 2]\n', 0, "bad_output"),
    ("", 0, "bad_output"),
    ('{"result": 1}\n', 3, "sandbox_exit_3"),
    ('{"result": 1}\n', 1, "sandbox_exit_1"),
])
async def test_the_failure_code_names_what_went_wrong_and_never_carries_text(pool, tenant_a, print_, code, error):
    async def program(proc: SandboxProcess) -> int:
        proc.stdout(print_)
        return code

    runtime, _ = make(pool, program)
    handle = await runtime.start(spec(tenant_a))
    result = await runtime.wait(handle.run_id)
    assert (result.status.state, result.status.error, result.output) == (RunState.FAILED, error, None)


async def test_only_stdout_is_the_output_and_only_its_last_line_counts(pool, tenant_a):
    async def program(proc: SandboxProcess) -> int:
        proc.stdout("progress line\n")
        proc.stdout(json.dumps({"result": {"answer": "x"}}) + "\n\n")
        proc.put(SandboxOutput("stderr", b'{"result": "from stderr"}\n'))
        return 0

    runtime, _ = make(pool, program)
    handle = await runtime.start(spec(tenant_a))
    assert (await runtime.wait(handle.run_id)).output == {"answer": "x"}


async def test_a_result_past_the_output_cap_is_not_read_so_a_runaway_program_cannot_fill_memory(pool, tenant_a, monkeypatch):
    monkeypatch.setattr(openshell_runtime, "MAX_OUTPUT_BYTES", 1000)

    async def program(proc: SandboxProcess) -> int:
        proc.stdout("x" * 5000 + "\n")
        proc.stdout(json.dumps({"result": 1}) + "\n")
        return 0

    runtime, _ = make(pool, program)
    handle = await runtime.start(spec(tenant_a))
    assert (await runtime.wait(handle.run_id)).status.error == "bad_output"


async def test_an_error_inside_the_driver_is_a_coded_failure_and_the_sandbox_is_still_destroyed(pool, owner_pool, tenant_a):
    class Broken(FakeSandboxDriver):
        async def run(self, launch):
            raise OSError("socket closed: secret-host.internal")
            yield  # pragma: no cover

    driver = Broken(await done())
    runtime = OpenShellAgentRuntime(driver, pool, config())
    handle = await runtime.start(spec(tenant_a))
    result = await runtime.wait(handle.run_id)
    assert (result.status.state, result.status.error) == (RunState.FAILED, "sandbox_error")
    assert "secret-host" not in repr(result) and driver.destroyed == [handle.run_id]
    [(_, exit_detail)] = [e for e in await events(owner_pool, handle.execution_id) if e[0] == "exit"]
    assert "secret-host" not in json.dumps(exit_detail)


# ---------------------------------------------------------------------------------------------- the event log

async def test_a_deny_is_written_while_the_run_is_still_going(pool, owner_pool, tenant_a):
    gate, seen = asyncio.Event(), []

    async def program(proc: SandboxProcess) -> int:
        proc.emit(SandboxEventKind.NETWORK_DENIED, {"host": "api.example.com", "port": 443})
        await gate.wait()
        return 0

    runtime, _ = make(pool, program, limits=SandboxLimits("1", "1Gi", 30))
    handle = await runtime.start(spec(tenant_a))
    for _ in range(100):
        seen = await events(owner_pool, handle.execution_id)
        if any(k == "network_denied" for k, _ in seen):
            break
        await asyncio.sleep(0.02)
    assert [k for k, _ in seen] == ["start", "network_denied"]  # visible to the Agent runs page before the run ends
    assert (await runtime.status(handle.run_id)).state is RunState.RUNNING
    gate.set()
    await runtime.wait(handle.run_id)


async def test_log_events_are_batched_and_written_in_order(pool, owner_pool, tenant_a):
    async def program(proc: SandboxProcess) -> int:
        for i in range(45):
            proc.emit(SandboxEventKind.LOG, {"message": f"line {i}"})
        return 0

    runtime, _ = make(pool, program)
    handle = await runtime.start(spec(tenant_a))
    await runtime.wait(handle.run_id)
    rows = await events(owner_pool, handle.execution_id)
    assert [k for k, _ in rows] == ["start"] + ["log"] * 45 + ["exit"]
    assert [d["message"] for k, d in rows if k == "log"] == [f"line {i}" for i in range(45)]


async def test_a_run_cannot_flood_the_table_and_its_exit_event_is_kept(pool, owner_pool, tenant_a):
    async def program(proc: SandboxProcess) -> int:
        for i in range(MAX_EVENTS_PER_RUN + 300):
            proc.emit(SandboxEventKind.LOG, {"message": f"line {i}"})
        return 0

    runtime, _ = make(pool, program)
    handle = await runtime.start(spec(tenant_a))
    await runtime.wait(handle.run_id)
    rows = await events(owner_pool, handle.execution_id)
    assert len(rows) <= MAX_EVENTS_PER_RUN + 2 and rows[-1][0] == "exit"
    assert any(d.get("message") == "further events were not kept" for _, d in rows)


async def test_secrets_and_unlisted_fields_never_reach_the_event_table(pool, owner_pool, tenant_a):
    async def program(proc: SandboxProcess) -> int:
        token = proc.env["RUN_TOKEN"]
        proc.emit(SandboxEventKind.LOG, {
            "message": f"calling with {token} and Bearer abc.def.ghi to https://x.test/?api_key=SECRET1", "environment": {"RUN_TOKEN": token},
            "stdin": "the user's question", "path": "/sandbox/work/" + "p" * 1000, "port": 8000,
        })
        return 0

    runtime, _ = make(pool, program)
    handle = await runtime.start(spec(tenant_a, context=await with_context(pool, tenant_a)))
    await runtime.wait(handle.run_id)
    dump = json.dumps(await events(owner_pool, handle.execution_id))
    secret = (await owner_pool.fetchval("SELECT prefix FROM run_tokens"))
    assert "abc.def.ghi" not in dump and "SECRET1" not in dump and "the user's question" not in dump and "environment" not in dump
    assert f"grt_{secret}_" not in dump and "[redacted]" in dump
    [(_, detail)] = [e for e in await events(owner_pool, handle.execution_id) if e[0] == "log"]
    assert len(detail["path"]) <= 160 and detail["port"] == 8000


async def test_a_failed_event_write_is_logged_and_does_not_fail_the_run(pool, tenant_a, monkeypatch, caplog):
    from adapters.sandbox_events import SandboxEventWriter

    async def broken(self, rows):
        raise asyncpg.PostgresConnectionError("down")

    monkeypatch.setattr(SandboxEventWriter, "write", broken)
    runtime, _ = make(pool, await done({"ok": 1}))
    handle = await runtime.start(spec(tenant_a))
    assert (await runtime.wait(handle.run_id)).status.state is RunState.SUCCEEDED  # the events are an observation, not the control record
    assert "sandbox events was not written" in caplog.text


async def test_the_events_of_two_runs_never_mix_and_a_retried_run_appends_to_its_own_log(pool, owner_pool, tenant_a):
    runtime, _ = make(pool, await done({"ok": 1}))
    first, second = await runtime.start(spec(tenant_a)), await runtime.start(spec(tenant_a))
    await runtime.wait(first.run_id), await runtime.wait(second.run_id)
    assert [k for k, _ in await events(owner_pool, first.execution_id)] == ["start", "exit"]
    assert [k for k, _ in await events(owner_pool, second.execution_id)] == ["start", "exit"]
    again = await runtime.start(spec(tenant_a, execution_id=first.execution_id))  # a job's next attempt
    await runtime.wait(again.run_id)
    assert [k for k, _ in await events(owner_pool, first.execution_id)] == ["start", "exit", "start", "exit"]


# ---------------------------------------------------------------------------------------------- stopping

async def test_stopping_a_run_destroys_the_sandbox_revokes_the_token_and_records_the_stop(pool, owner_pool, tenant_a):
    started = asyncio.Event()
    cancelled = []

    async def program(proc: SandboxProcess) -> int:
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return 0

    runtime, driver = make(pool, program, limits=SandboxLimits("1", "1Gi", 60))
    handle = await runtime.start(spec(tenant_a, context=await with_context(pool, tenant_a)))
    await asyncio.wait_for(started.wait(), 5)
    status = await runtime.stop(handle.run_id)
    assert status.state is RunState.STOPPED and cancelled == [True]
    assert driver.destroyed == [handle.run_id] and driver.live == set()
    assert await owner_pool.fetchval("SELECT revoked_at IS NOT NULL FROM run_tokens")
    rows = await events(owner_pool, handle.execution_id)
    assert [k for k, _ in rows] == ["start", "exit"] and rows[-1][1] == {"reason": "stopped"}


async def test_a_run_that_is_stopped_before_it_started_never_creates_a_sandbox_or_a_token(pool, owner_pool, tenant_a):
    runtime, driver = make(pool, await done({"ok": 1}))
    handle = await runtime.start(spec(tenant_a, context=await with_context(pool, tenant_a)))
    status = await runtime.stop(handle.run_id)  # no await in between: the task has not run
    assert status.state is RunState.STOPPED
    assert driver.launches == [] and await owner_pool.fetchval("SELECT count(*) FROM run_tokens") == 0
    assert await owner_pool.fetchval("SELECT count(*) FROM sandbox_events") == 0


async def test_starting_a_run_that_is_still_running_is_refused(pool, tenant_a):
    release = asyncio.Event()

    async def program(proc: SandboxProcess) -> int:
        await release.wait()
        return 0

    runtime, _ = make(pool, program, limits=SandboxLimits("1", "1Gi", 60))
    run = uuid4()
    await runtime.start(spec(tenant_a, execution_id=run))
    with pytest.raises(ValueError, match="already exists"):
        await runtime.start(spec(tenant_a, execution_id=run))
    release.set()
    await runtime.wait(str(run))


# ---------------------------------------------------------------------------------------------- the check probe

async def probe(proc: SandboxProcess, *, network: str = "failed (URLError)", read: str = "failed (PermissionError)") -> int:
    proc.stdout(json.dumps({"result": {"provider_call": network, "outside_read": read, "outside_path": proc.env.get("CHECK_OUTSIDE_PATH", "/var/lib/dpkg/status")}}) + "\n")
    return 0


async def test_when_the_stream_carried_no_denial_the_probe_report_becomes_the_event_and_says_so(pool, owner_pool, tenant_a):
    """OpenShell logs a refused connection but not a refused file read, so the probe's own word is recorded, marked as such."""
    runtime, driver = make(pool, probe)
    handle = await runtime.start(RunSpec(kind=openshell_runtime.SANDBOX_CHECK_KIND, input={"outside_path": "/srv/data"}, tenant_id=UUID(tenant_a.id)))
    assert (await runtime.wait(handle.run_id)).status.state is RunState.SUCCEEDED
    assert driver.launches[0].env["CHECK_OUTSIDE_PATH"] == "/srv/data" and driver.launches[0].command[-1] == "check"
    rows = await events(owner_pool, handle.execution_id)
    assert [k for k, _ in rows] == ["start", "network_denied", "file_denied", "exit"]
    assert rows[1][1] == {"host": "api.openai.com", "port": 443, "reason": "agent_check"}  # a refused connection keeps host, port, reason
    assert rows[2][1]["source"] == "agent_check" and rows[2][1]["path"] == "/srv/data"


async def test_a_denial_the_sandbox_reported_is_not_recorded_a_second_time_from_the_probe(pool, owner_pool, tenant_a):
    async def both(proc: SandboxProcess) -> int:
        proc.emit(SandboxEventKind.NETWORK_DENIED, {"host": "api.openai.com", "port": 443})
        proc.emit(SandboxEventKind.FILE_DENIED, {"path": "/var/lib/dpkg/status"})
        return await probe(proc)

    runtime, _ = make(pool, both)
    handle = await runtime.start(RunSpec(kind=openshell_runtime.SANDBOX_CHECK_KIND, input={}, tenant_id=UUID(tenant_a.id)))
    await runtime.wait(handle.run_id)
    rows = await events(owner_pool, handle.execution_id)
    assert [k for k, _ in rows] == ["start", "network_denied", "file_denied", "exit"]
    assert all("source" not in d for k, d in rows if k.endswith("denied"))  # these came from the sandbox


async def test_a_probe_that_got_through_or_failed_for_another_reason_records_no_denial(pool, owner_pool, tenant_a):
    async def leaky(proc: SandboxProcess) -> int:
        return await probe(proc, network="succeeded", read="failed (FileNotFoundError)")

    runtime, _ = make(pool, leaky)
    handle = await runtime.start(RunSpec(kind=openshell_runtime.SANDBOX_CHECK_KIND, input={}, tenant_id=UUID(tenant_a.id)))
    result = await runtime.wait(handle.run_id)
    assert result.output["provider_call"] == "succeeded"
    assert [k for k, _ in await events(owner_pool, handle.execution_id)] == ["start", "exit"]


async def test_a_normal_run_never_gets_events_made_up_from_its_output(pool, owner_pool, tenant_a):
    runtime, _ = make(pool, await done({"provider_call": "failed (URLError)", "outside_read": "failed (PermissionError)"}))
    handle = await runtime.start(spec(tenant_a))
    await runtime.wait(handle.run_id)
    assert [k for k, _ in await events(owner_pool, handle.execution_id)] == ["start", "exit"]

"""One contract for every `SandboxDriver`: what `run` yields, in which order, and what is left behind when it ends.

Two drivers pass it here: the fake sandbox (tests/fake_sandbox.py) and the OpenShell SDK driver with stand-ins for the SDK
client (tests/support/openshell_stub.py). The OpenShell driver against a real gateway is NOT a pytest: it is
`scripts/verify/openshell.sh` (a skipped test would be a new skip, and the real run needs a Linux host with Docker).
"""
import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.openshell_driver import OpenShellSdkDriver, sandbox_name
from ports import (
    EgressRule,
    SandboxEvent,
    SandboxEventKind,
    SandboxExit,
    SandboxLaunch,
    SandboxLimits,
    SandboxOutput,
    SandboxPolicy,
    SandboxUnavailable,
)
from tests.fake_sandbox import FakeSandboxDriver, SandboxProcess
from tests.support.openshell_stub import Client, ExecChunk, ExecResult, Messages, WatchEvent

DENIED_LINE = "NET:OPEN [MED] DENIED /usr/bin/python3.10(0) -> api.example.com:443 [reason:transparent_tcp_policy_denied]"


class Harness:
    """Scripts a run the same way for each driver, and says what the driver left behind."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.script_args: dict = {}
        self.clients: list[Client] = []
        self.gate = threading.Event()
        self.fake_release = asyncio.Event()
        self.fake = FakeSandboxDriver(self._fake_program) if kind == "fake" else None
        self.sdk = None

    # ---- the script
    def script(self, *, stdout=b"", stderr=b"", denial=False, code=0, block=False, unavailable=False) -> None:
        self.script_args = dict(stdout=stdout, stderr=stderr, denial=denial, code=code, block=block, unavailable=unavailable)

    async def _fake_program(self, proc: SandboxProcess) -> int:
        a = self.script_args
        if a["stderr"]:
            proc.put(SandboxOutput("stderr", a["stderr"]))
        if a["denial"]:
            proc.emit(SandboxEventKind.NETWORK_DENIED, {"host": "api.example.com", "port": 443})
        if a["stdout"]:
            proc.stdout(a["stdout"].decode())
        if a["block"]:
            await self.fake_release.wait()
        return a["code"]

    def driver(self):
        if self.fake is not None:
            self.fake._unavailable = self.script_args.get("unavailable", False)
            return self.fake
        a = self.script_args
        items = ([ExecChunk("stderr", a["stderr"])] if a["stderr"] else []) + ([ExecChunk("stdout", a["stdout"])] if a["stdout"] else [])
        now = SimpleNamespace(ToDatetime=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
        watch = [WatchEvent(log=SimpleNamespace(level="INFO", message=DENIED_LINE, fields={}, event_time=now))] if a["denial"] else []

        def make(_sdk):
            client = Client(exec_items=[*items, ExecResult(a["code"])], fail_at="create" if a["unavailable"] else None,
                            block_exec=self.gate if a["block"] else None, watch=watch)
            self.clients.append(client)
            return client

        self.sdk = OpenShellSdkDriver(endpoint=None, workspace="default", sdk=SimpleNamespace(ExecChunk=ExecChunk), client_factory=make, messages=Messages())
        return self.sdk

    # ---- what is left behind
    def live(self, run_id: str) -> bool:
        if self.fake is not None:
            return run_id in self.fake.live
        return run_id in self.sdk._clients  # type: ignore[union-attr]

    def deleted(self) -> bool:
        if self.fake is not None:
            return True  # the fake's sandbox is its temporary directory, removed when the stream ends
        return all(any(c[0] == "delete" for c in client.calls) and client.closed for client in self.clients)


@pytest.fixture(params=["fake", "openshell-sdk-stub"])
def harness(request):
    return Harness("fake" if request.param == "fake" else "sdk")


def launch(run_id: str | None = None) -> SandboxLaunch:
    return SandboxLaunch(
        run_id=run_id or str(uuid4()), command=("python3", "-c", "pass"),
        policy=SandboxPolicy(egress=(EgressRule("gateway.test", 8000),), work_dir="/sandbox/work", limits=SandboxLimits("1", "512Mi", 30),
                             read_only=("/usr",), network_binaries=("/usr/bin/python3*",)),
        env={"RUN_TOKEN": "grt_secret_value"}, stdin=b"the question",
    )


async def collect(driver, run: SandboxLaunch):
    return [m async for m in driver.run(run)]


async def test_a_run_ends_with_exactly_one_exit_and_nothing_after_it(harness):
    harness.script(stdout=b'{"result": 1}\n')
    messages = await collect(harness.driver(), launch())
    exits = [i for i, m in enumerate(messages) if isinstance(m, SandboxExit)]
    assert exits == [len(messages) - 1] and messages[-1] == SandboxExit(0)


async def test_output_arrives_in_its_own_stream_and_intact(harness):
    harness.script(stdout=b"line one\nline two\n", stderr=b"a warning\n")
    messages = await collect(harness.driver(), launch())
    out = b"".join(m.data for m in messages if isinstance(m, SandboxOutput) and m.stream == "stdout")
    err = b"".join(m.data for m in messages if isinstance(m, SandboxOutput) and m.stream == "stderr")
    assert (out, err) == (b"line one\nline two\n", b"a warning\n")


async def test_a_refused_connection_is_an_event_that_comes_before_the_exit(harness):
    harness.script(denial=True, stdout=b"x")
    messages = await collect(harness.driver(), launch())
    events = [m for m in messages if isinstance(m, SandboxEvent)]
    assert [e.kind for e in events] == [SandboxEventKind.NETWORK_DENIED] and events[0].detail["host"] == "api.example.com"
    assert events[0].at.tzinfo is not None
    assert messages.index(events[0]) < messages.index(SandboxExit(0))


async def test_a_nonzero_exit_status_is_a_result_not_an_exception(harness):
    harness.script(code=7)
    assert (await collect(harness.driver(), launch()))[-1] == SandboxExit(7)


async def test_the_sandbox_is_gone_when_the_stream_ends(harness):
    run = launch()
    harness.script(stdout=b"x")
    await collect(harness.driver(), run)
    assert not harness.live(run.run_id) and harness.deleted()


async def test_cancelling_the_reader_stops_the_run_and_releases_the_sandbox(harness):
    run = launch()
    harness.script(block=True)
    driver = harness.driver()

    async def read():
        async for _ in driver.run(run):
            pass

    task = asyncio.create_task(read())
    for _ in range(100):
        await asyncio.sleep(0.02)
        if harness.live(run.run_id):
            break
    assert harness.live(run.run_id)  # it was running
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    harness.fake_release.set()
    harness.gate.set()
    assert not harness.live(run.run_id) and harness.deleted()


async def test_a_sandbox_that_cannot_start_raises_unavailable_and_leaves_nothing(harness):
    run = launch()
    harness.script(unavailable=True)
    with pytest.raises(SandboxUnavailable):
        await collect(harness.driver(), run)
    assert not harness.live(run.run_id)


async def test_destroy_is_safe_twice_and_for_a_run_that_never_existed(harness):
    harness.script(stdout=b"x")
    driver = harness.driver()
    run = launch()
    await collect(driver, run)
    await driver.destroy(run.run_id)
    await driver.destroy(run.run_id)
    await driver.destroy(str(uuid4()))


def test_what_a_launch_holds_that_is_secret_is_not_in_its_repr():
    text = repr(launch())
    assert "grt_secret_value" not in text and "the question" not in text


def test_the_openshell_name_of_a_sandbox_is_stable_for_a_run():
    run_id = str(uuid4())
    assert sandbox_name(run_id) == sandbox_name(run_id) and len(sandbox_name(run_id)) <= 19

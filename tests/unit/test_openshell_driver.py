"""The OpenShell SDK driver against stand-ins for the SDK client (no gateway, no sandbox).

This proves the driver's own logic: the order of the calls, the policy it asks for, events and output crossing from the
SDK's thread to the event loop, the exit code, and that the sandbox is deleted however the run ends. It does NOT prove that
a real OpenShell gateway accepts the policy or behaves this way: that is `scripts/verify/openshell.sh`, not run here.
"""
import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.openshell_driver import NAME_LENGTH, OpenShellSdkDriver, sandbox_name
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
from tests.support.openshell_stub import Client, ExecChunk, ExecResult, Messages, WatchEvent

pytestmark = pytest.mark.unit


def launch():
    return SandboxLaunch(
        run_id="11111111-2222-4333-8444-555555555555", command=("python3", "-c", "pass", "answer"),
        policy=SandboxPolicy(egress=(EgressRule("gateway.internal", 8000),), work_dir="/sandbox/work", limits=SandboxLimits("1", "512Mi", 60), read_only=("/usr",), network_binaries=("/usr/bin/python3*",)),
        env={"RUN_TOKEN": "grt_x"}, stdin=b"{}",
    )


def driver(client):
    sdk = SimpleNamespace(ExecChunk=ExecChunk)
    return OpenShellSdkDriver(endpoint="gateway:50051", workspace="default", image="img:1", sdk=sdk, client_factory=lambda s: client, messages=Messages())


async def collect(d, launch_):
    return [m async for m in d.run(launch_)]


async def test_a_run_creates_the_sandbox_with_the_policy_runs_the_command_and_deletes_it():
    now = datetime.now(timezone.utc)
    log = SimpleNamespace(level="WARN", message="network connection denied", fields={"host": "api.example.com", "port": "443"}, event_time=SimpleNamespace(ToDatetime=lambda: now.replace(tzinfo=None)))
    client = Client(exec_items=[ExecChunk("stdout", b"hello\n"), ExecChunk("stderr", b"warn\n"), ExecResult(0)], watch=[WatchEvent(log=log)])
    messages = await collect(driver(client), launch())
    outputs = [m for m in messages if isinstance(m, SandboxOutput)]
    assert [(o.stream, o.data) for o in outputs] == [("stdout", b"hello\n"), ("stderr", b"warn\n")]
    assert messages[-1] == SandboxExit(0)
    steps = [c[0] for c in client.calls]
    assert steps[:4] == ["template.create", "create", "ready", "exec"] and "exec_stream" in steps
    assert steps.index("exec_stream") < steps.index("delete") and "template.delete" in steps and client.closed
    create = next(c for c in client.calls if c[0] == "create")[1]
    name = sandbox_name(launch().run_id)
    assert create["name"] == name and create["workload_template"] == name and len(name) <= NAME_LENGTH
    assert next(c for c in client.calls if c[0] == "template.create")[1]["name"] == name
    assert ("delete", name) == next(c[:2] for c in client.calls if c[0] == "delete")
    assert create["spec"].policy.routes == [("gateway.internal", 8000)] and create["spec"].policy.read_write == ["/sandbox/work"]
    assert create["spec"].policy.binaries == ["/usr/bin/python3*"]  # only the interpreter may open the route
    template = next(c for c in client.calls if c[0] == "template.create")[1]
    assert (template["cpu"], template["memory"], template["image"]) == ("1", "512Mi", "img:1")
    stream = next(c for c in client.calls if c[0] == "exec_stream")
    assert stream[1] == ["python3", "-c", "pass", "answer"] and stream[2]["workdir"] == "/sandbox/work"
    assert stream[2]["env"] == {"RUN_TOKEN": "grt_x"} and stream[2]["stdin"] == b"{}" and 60 < stream[2]["timeout_seconds"] <= 90


def test_the_sandbox_name_fits_the_limit_the_gateway_enforces_and_stays_unique_per_run():
    ids = [str(uuid4()) for _ in range(200)]
    names = {sandbox_name(i) for i in ids}
    assert len(names) == 200 and all(len(n) == NAME_LENGTH and n.isalnum() and n == n.lower() for n in names)
    assert sandbox_name("11111111-2222-4333-8444-555555555555") == "r1111111122224333844"[:NAME_LENGTH]


async def test_the_work_directory_must_already_be_in_the_image_and_the_driver_checks_before_the_command_runs():
    client = Client(exec_items=[ExecResult(0)])
    await collect(driver(client), launch())
    assert ("exec", ["test", "-d", "/sandbox/work"]) in client.calls
    assert [c[0] for c in client.calls].index("exec") < [c[0] for c in client.calls].index("exec_stream")
    missing = Client(exec_items=[ExecResult(0)], work_dir_exit=1)
    with pytest.raises(SandboxUnavailable, match="no work directory /sandbox/work"):
        await collect(driver(missing), launch())
    assert "exec_stream" not in [c[0] for c in missing.calls] and "delete" in [c[0] for c in missing.calls]


async def test_events_from_the_watch_stream_are_classified_and_passed_on():
    now = datetime.now(timezone.utc)
    stamp = SimpleNamespace(ToDatetime=lambda: now.replace(tzinfo=None))
    log = SimpleNamespace(level="WARN", message="egress denied", fields={"dst_host": "api.example.com"}, event_time=stamp)
    platform = SimpleNamespace(type="Normal", reason="Started", message="container started", metadata={}, event_time=stamp)
    client = Client(exec_items=[ExecResult(0)], watch=[WatchEvent(log=log), WatchEvent(event=platform)])
    messages = await collect(driver(client), launch())
    events = [m for m in messages if isinstance(m, SandboxEvent)]
    assert [e.kind for e in events] == [SandboxEventKind.NETWORK_DENIED]  # the Started platform event is plumbing: no row
    assert events[0].detail["host"] == "api.example.com" and events[0].at.tzinfo is not None


async def test_a_nonzero_exit_is_a_result_not_an_exception():
    messages = await collect(driver(Client(exec_items=[ExecResult(3)])), launch())
    assert messages[-1] == SandboxExit(3)


@pytest.mark.parametrize("step", ["create", "ready"])
async def test_a_sandbox_that_cannot_start_raises_unavailable_and_is_still_deleted(step):
    client = Client(fail_at=step)
    with pytest.raises(SandboxUnavailable) as caught:
        await collect(driver(client), launch())
    assert "grt_x" not in str(caught.value)  # the message never carries the token
    assert "delete" in [c[0] for c in client.calls] and client.closed


async def test_a_stream_that_ends_without_an_exit_status_is_unavailable():
    with pytest.raises(SandboxUnavailable):
        await collect(driver(Client(exec_items=[ExecChunk("stdout", b"x")])), launch())


async def test_cancelling_the_run_deletes_the_sandbox_which_ends_the_blocked_call():
    gate = threading.Event()
    client = Client(block_exec=gate)
    d = driver(client)

    async def consume():
        async for _ in d.run(launch()):
            pass

    task = asyncio.create_task(consume())
    for _ in range(100):
        if "exec_stream" in [c[0] for c in client.calls]:
            break
        await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gate.is_set() and "delete" in [c[0] for c in client.calls] and client.closed


async def test_destroy_is_safe_twice_and_for_a_run_that_never_started():
    d = driver(Client())
    await d.destroy("never-started")
    await d.destroy("never-started")


async def test_without_the_sdk_installed_the_driver_says_so_and_names_the_pinned_version(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "openshell":
            raise ImportError("No module named 'openshell'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(SandboxUnavailable) as caught:
        await collect(OpenShellSdkDriver(endpoint=None, workspace="default"), launch())
    assert "openshell==0.1.2" in str(caught.value)

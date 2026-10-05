"""Stand-ins for the OpenShell SDK client, its messages and its stream, so the driver can run without a gateway.

Used by the driver's unit tests and by the SandboxDriver contract suite. These are NOT recordings of the SDK: they follow the
calls the driver makes (checked against the 0.1.2 wheel by `scripts/verify/openshell_sdk_surface.py`)."""
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from adapters.openshell_driver import SdkMessages


@dataclass
class ExecChunk:
    stream: str
    data: bytes


@dataclass
class ExecResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class Templates:
    def __init__(self, calls):
        self.calls = calls

    def create(self, **kw):
        self.calls.append(("template.create", kw))

    def delete(self, name, **kw):
        self.calls.append(("template.delete", name, kw))


class WatchEvent:
    def __init__(self, log=None, event=None):
        self._log, self._event = log, event

    def HasField(self, name):  # noqa: N802 (the protobuf spelling)
        return (name == "log" and self._log is not None) or (name == "event" and self._event is not None)

    log = property(lambda self: self._log)
    event = property(lambda self: self._event)


class Client:
    def __init__(self, *, exec_items=(), fail_at=None, block_exec=None, watch=(), work_dir_exit=0):
        self.work_dir_exit = work_dir_exit
        self.calls: list[Any] = []
        self.exec_items = list(exec_items)
        self.fail_at = fail_at
        self.block_exec = block_exec
        self.closed = False
        self._stub = SimpleNamespace(WatchSandbox=lambda request: iter(list(watch)))

    def _maybe_fail(self, step):
        if self.fail_at == step:
            raise RuntimeError(f"{step} failed")

    def sandbox_templates(self):
        return Templates(self.calls)

    def create_from_template(self, **kw):
        self.calls.append(("create", kw))
        self._maybe_fail("create")

    def wait_ready(self, name, **kw):
        self.calls.append(("ready", name))
        self._maybe_fail("ready")

    def exec(self, name, command, **kw):
        self.calls.append(("exec", command))
        return ExecResult(self.work_dir_exit if command[0] == "test" else 0)

    def exec_stream(self, name, command, **kw):
        self.calls.append(("exec_stream", command, kw))
        if self.block_exec is not None:
            self.block_exec.wait(5)  # the SDK call blocks until the sandbox is deleted
            raise RuntimeError("stream closed")
        yield from self.exec_items

    def delete(self, name, **kw):
        self.calls.append(("delete", name, kw))
        if self.block_exec is not None:
            self.block_exec.set()

    def close(self):
        self.closed = True


class Messages(SdkMessages):
    """Plain objects in place of protobuf messages, so no SDK is needed."""

    def policy(self, launch):
        p = launch.policy
        return SimpleNamespace(routes=[(e.host, e.port) for e in p.egress], read_write=[p.work_dir], read_only=list(p.read_only), binaries=list(p.network_binaries))

    def spec(self, launch):
        return SimpleNamespace(policy=self.policy(launch))

    def watch_request(self, workspace, name):
        return SimpleNamespace(workspace=workspace, name=name)

"""A fake `SandboxDriver` for the tests (Sprint 009).

NOT a recording of a real OpenShell run: no sandbox could run in this container. It follows the `SandboxDriver` port and
enforces the same policy a real sandbox is given: the only place the program may connect to is the policy's egress route,
the only readable places are the work directory and the listed system paths, and a program can hit a limit. A refusal
raises in the program (as a refused connection or a permission error would) and is reported as an event, the way the
real driver reports what OpenShell streams.

The program that "runs inside" is a coroutine the test gives. `entry_program` runs the real `sandbox_agent/entry.py`
in it, with its network and file calls going through those policy checks and its HTTP calls into the real app.
"""
import asyncio
import io
import os
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from ports.sandbox import (
    SandboxEvent,
    SandboxEventKind,
    SandboxExit,
    SandboxLaunch,
    SandboxMessage,
    SandboxOutput,
    SandboxUnavailable,
)

_END = object()


class SandboxProcess:
    """What the program inside the fake sandbox can do. Every action goes through the policy."""

    def __init__(self, launch: SandboxLaunch, queue: "asyncio.Queue[Any]", real_work_dir: str) -> None:
        self.launch = launch
        self.env = dict(launch.env)
        self.stdin = launch.stdin.decode("utf-8")
        self.policy = launch.policy
        self.real_work_dir = real_work_dir  # the test's own directory behind the policy's work directory
        self._queue = queue
        self._loop = asyncio.get_running_loop()

    def put(self, item: Any) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, item)  # the program may call from a thread

    def emit(self, kind: SandboxEventKind, detail: dict[str, Any] | None = None) -> None:
        self.put(SandboxEvent(kind, datetime.now(timezone.utc), detail or {}))

    def stdout(self, text: str) -> None:
        self.put(SandboxOutput("stdout", text.encode("utf-8")))

    def check_egress(self, host: str, port: int) -> None:
        if not any(rule.host == host and rule.port == port for rule in self.policy.egress):
            self.emit(SandboxEventKind.NETWORK_DENIED, {"host": host, "port": port, "protocol": "tcp"})
            raise ConnectionRefusedError(f"connection to {host}:{port} was refused by the sandbox policy")

    def resolve_path(self, path: str) -> str:
        """The real path for a read or write. Outside the work directory and the listed system paths it is refused."""
        work = self.policy.work_dir.rstrip("/")
        if path == work or path.startswith(work + "/"):
            return os.path.join(self.real_work_dir, path[len(work):].lstrip("/"))
        if any(path == ro or path.startswith(ro.rstrip("/") + "/") for ro in self.policy.read_only):
            return path
        self.emit(SandboxEventKind.FILE_DENIED, {"path": path, "syscall": "open"})
        raise PermissionError(f"access to {path} was refused by the sandbox policy")

    def hit_limit(self, limit: str, value: Any = None) -> None:
        self.emit(SandboxEventKind.LIMIT_HIT, {"limit": limit, "value": value if value is not None else ""})


Program = Callable[[SandboxProcess], Awaitable[int]]


class FakeSandboxDriver:
    def __init__(self, program: Program, *, unavailable: bool = False) -> None:
        self.program = program  # a test may swap it between runs
        self._unavailable = unavailable
        self.launches: list[SandboxLaunch] = []
        self.destroyed: list[str] = []
        self.live: set[str] = set()

    async def run(self, launch: SandboxLaunch) -> AsyncIterator[SandboxMessage]:
        if self._unavailable:
            raise SandboxUnavailable("no sandbox gateway")
        self.launches.append(launch)
        self.live.add(launch.run_id)
        queue: asyncio.Queue[Any] = asyncio.Queue()
        with tempfile.TemporaryDirectory(prefix="fake-sandbox-") as work:
            process = SandboxProcess(launch, queue, work)

            async def main() -> None:
                try:
                    code = await self.program(process)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    code = 1
                process.put(SandboxExit(code))  # the same path as every other message, so the order is kept
                process.put(_END)

            task = asyncio.create_task(main())
            try:
                while True:
                    item = await queue.get()
                    if item is _END:
                        return
                    yield item
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                self.live.discard(launch.run_id)

    async def destroy(self, run_id: str) -> None:
        self.destroyed.append(run_id)
        self.live.discard(run_id)


def entry_program(call_gateway: Callable[[str, dict[str, Any], dict[str, str]], tuple[int, dict[str, Any]]]) -> Program:
    """Run the real `sandbox_agent/entry.py` inside the fake sandbox.

    `call_gateway(path, body, headers)` is a blocking call into the app (the entry is synchronous, so it runs in a
    thread). The entry's network call goes through the policy: only the gateway's host and port are reachable, and the
    URL it asks for decides which. Its file calls go through the policy too.
    """
    from sandbox_agent import entry

    async def program(proc: SandboxProcess) -> int:
        command = proc.launch.command[-1]

        def post(url: str, body: dict[str, Any], headers: Any) -> tuple[int, dict[str, Any]]:
            parsed = urlparse(url)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            proc.check_egress(parsed.hostname or "", port)
            return call_gateway(parsed.path, body, dict(headers))

        def open_file(path: str, mode: str = "r", **kwargs: Any) -> Any:
            return open(proc.resolve_path(str(path)), mode, **kwargs)  # noqa: SIM115 (the caller uses it as a context manager)

        out, err = io.StringIO(), io.StringIO()
        code = await asyncio.to_thread(
            entry.main, [command], proc.env, io.StringIO(proc.stdin), out, err, post, open_file,
        )
        proc.stdout(out.getvalue())
        return code

    return program


def blocking_gateway_caller(client: Callable[[], Any], loop: Callable[[], Any]) -> Callable[[str, dict[str, Any], dict[str, str]], tuple[int, dict[str, Any]]]:
    """A blocking call into an app through its `httpx.AsyncClient`, for the entry program (which runs in a thread).
    `client` and `loop` are read at call time, so the app may be built after the driver."""

    def call(path: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        future = asyncio.run_coroutine_threadsafe(client().post(path, json=body, headers=headers), loop())
        response = future.result(60)
        return response.status_code, response.json()

    return call

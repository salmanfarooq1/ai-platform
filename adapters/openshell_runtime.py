"""The OpenShell AgentRuntime: each run executes inside a sandbox (Sprint 009, ADR-0009).

`start` mints a run token (bound to the run's `execution_id`, valid for a short time, only its hash is stored) and hands
the sandbox one command with `GATEWAY_URL`, `RUN_TOKEN`, `EXECUTION_ID` and `WORK_DIR`. The sandbox policy gives it one
network route (the gateway), one writable directory and CPU, memory and wall-clock limits. Everything the agent does
that matters goes through the gateway over HTTP, so `enforce()` decides it and records it with the run's `execution_id`.

The sandbox itself is behind the `SandboxDriver` port (`ports/sandbox.py`). The runtime writes a `start` event, then the
events the driver yields, then an `exit` event, to `sandbox_events` in batches. The run's output is the JSON the agent
prints as its last stdout line. A run keeps no text of an error: a failed run has a code (`sandbox_exit_<n>`,
`wall_time_exceeded`, `sandbox_unavailable`, `sandbox_error`, `bad_output`), because text could hold a secret.

Like the in-process runtime, this one tracks runs in memory. In a deployment it runs inside a worker, and the job row is
the durable status (the API queues the run: ADR-0011).
"""
import asyncio
import dataclasses
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from adapters.sandbox_events import MAX_EVENTS_PER_RUN, EventRow, SandboxEventWriter, to_row
from core.database.tenant import DbPool
from core.identity.run_tokens import issue_run_token, revoke_run_tokens
from ports.runtime import RunHandle, RunNotFound, RunResult, RunSpec, RunState, RunStatus
from ports.sandbox import (
    EgressRule,
    SandboxDriver,
    SandboxEvent,
    SandboxEventKind,
    SandboxExit,
    SandboxLaunch,
    SandboxLimits,
    SandboxOutput,
    SandboxPolicy,
    SandboxUnavailable,
)

logger = logging.getLogger("adapters.openshell_runtime")

SANDBOX_CHECK_KIND = "agent.sandbox_check"  # the A3 and A4 probe (`sandbox_agent/entry.py check`), never started by a route
MAX_OUTPUT_BYTES = 1_048_576
KILLED_EXIT = 137
TOKEN_TTL_MARGIN_SECONDS = 60
BATCH_SIZE = 20
FLUSH_SECONDS = 0.5


def load_entry_source() -> str:
    """The text of `sandbox_agent/entry.py`. The sandbox runs it with `python3 -c`, so the image needs python3 and nothing else."""
    import sandbox_agent.entry

    return Path(sandbox_agent.entry.__file__).read_text(encoding="utf-8")


@dataclasses.dataclass(frozen=True)
class SandboxConfig:
    gateway_url: str
    egress: EgressRule  # the gateway's host and port: the only place the sandbox may connect to
    limits: SandboxLimits
    work_dir: str
    read_only: tuple[str, ...] = ()
    network_binaries: tuple[str, ...] = ()
    entry_source: str = ""
    python: str = "python3"


class _Entry:
    def __init__(self, status: RunStatus) -> None:
        self.status = status
        self.output: Any = None
        self.task: asyncio.Task[None] | None = None
        self.done = asyncio.Event()


class OpenShellAgentRuntime:
    def __init__(self, driver: SandboxDriver, pool: DbPool, config: SandboxConfig, max_tracked: int = 1000) -> None:
        self._driver = driver
        self._pool = pool
        self._config = config
        self._max_tracked = max_tracked
        self._runs: OrderedDict[str, _Entry] = OrderedDict()

    # ------------------------------------------------------------------ start and the run itself

    async def start(self, spec: RunSpec) -> RunHandle:
        execution_id = spec.execution_id or uuid4()
        spec = dataclasses.replace(spec, execution_id=execution_id)
        run_id = str(execution_id)
        existing = self._runs.get(run_id)
        if existing is not None and not existing.status.state.terminal:
            raise ValueError(f"run {run_id} already exists")  # a finished run id may start again (a job's next attempt)
        self._runs.pop(run_id, None)
        entry = _Entry(RunStatus(
            run_id=run_id, execution_id=execution_id, tenant_id=spec.tenant_id, kind=spec.kind,
            state=RunState.RUNNING, started_at=datetime.now(timezone.utc),
        ))
        self._runs[run_id] = entry
        entry.task = asyncio.create_task(self._execute(entry, spec))
        self._evict()
        return RunHandle(run_id=run_id, execution_id=execution_id)

    def _launch(self, spec: RunSpec, execution_id: UUID, token: str | None) -> SandboxLaunch:
        cfg = self._config
        command = "check" if spec.kind == SANDBOX_CHECK_KIND else "answer"
        env = {"GATEWAY_URL": cfg.gateway_url, "EXECUTION_ID": str(execution_id), "WORK_DIR": cfg.work_dir}
        outside = spec.input.get("outside_path")
        if spec.kind == SANDBOX_CHECK_KIND and isinstance(outside, str) and outside.startswith("/"):
            env["CHECK_OUTSIDE_PATH"] = outside  # the check reads this file instead of its default
        if token is not None:
            env["RUN_TOKEN"] = token
        return SandboxLaunch(
            run_id=str(execution_id),
            command=(cfg.python, "-c", cfg.entry_source or load_entry_source(), command),
            policy=SandboxPolicy(egress=(cfg.egress,), work_dir=cfg.work_dir, limits=cfg.limits, read_only=cfg.read_only, network_binaries=cfg.network_binaries),
            env=env,
            stdin=json.dumps({"input": spec.input}).encode("utf-8"),
        )

    async def _mint_token(self, spec: RunSpec, execution_id: UUID) -> str | None:
        """A run token for runs that came with an enforcement context. A run with none has no way to call the gateway."""
        ctx = spec.context
        principal = getattr(ctx, "principal", None)
        boundary = getattr(ctx, "boundary", None)
        if principal is None or boundary is None:
            return None
        ttl = self._config.limits.wall_seconds + TOKEN_TTL_MARGIN_SECONDS
        issued = await issue_run_token(self._pool, principal, execution_id, boundary.to_payload(), ttl)
        return issued.token

    async def _execute(self, entry: _Entry, spec: RunSpec) -> None:
        execution_id = entry.status.execution_id
        writer = SandboxEventWriter(self._pool, spec.tenant_id, execution_id)
        events = _Batcher(writer, execution_id)
        state, error = RunState.FAILED, None
        exit_detail: dict[str, Any] = {}
        token: str | None = None
        try:
            token = await self._mint_token(spec, execution_id)
            launch = self._launch(spec, execution_id, token)
            events.add(SandboxEvent(SandboxEventKind.START, datetime.now(timezone.utc), {
                "limit": f"cpu {self._config.limits.cpu}, memory {self._config.limits.memory}, wall {self._config.limits.wall_seconds}s",
                "host": self._config.egress.host, "port": self._config.egress.port,
            }), (token,))
            await events.flush()
            state, error, exit_detail = await self._consume(entry, launch, events, (token,))
        except asyncio.CancelledError:
            state, error, exit_detail = RunState.STOPPED, None, {"reason": "stopped"}
            raise
        except SandboxUnavailable:
            logger.error("run %s: the sandbox could not start", execution_id, exc_info=True)
            state, error, exit_detail = RunState.FAILED, "sandbox_unavailable", {"reason": "sandbox_unavailable"}
        except Exception:
            logger.error("run %s failed", execution_id, exc_info=True)
            state, error, exit_detail = RunState.FAILED, "sandbox_error", {"reason": "sandbox_error"}
        finally:
            await self._finish(entry, spec, events, token, state, error, exit_detail)

    async def _consume(
        self, entry: _Entry, launch: SandboxLaunch, events: "_Batcher", secrets: tuple[str | None, ...],
    ) -> tuple[RunState, str | None, dict[str, Any]]:
        out = bytearray()
        code: int | None = None
        wall = self._config.limits.wall_seconds
        try:
            async with asyncio.timeout(wall):
                async for message in self._driver.run(launch):
                    if isinstance(message, SandboxEvent):
                        events.add(message, secrets)
                        if _is_loud(message):
                            await events.flush()
                        else:
                            await events.flush_if_due()
                    elif isinstance(message, SandboxOutput):
                        if message.stream == "stdout" and len(out) < MAX_OUTPUT_BYTES:
                            out += message.data[: MAX_OUTPUT_BYTES - len(out)]
                    elif isinstance(message, SandboxExit):
                        code = message.code
        except TimeoutError:
            events.add(SandboxEvent(SandboxEventKind.LIMIT_HIT, datetime.now(timezone.utc), {"limit": "wall_seconds", "value": wall}))
            return RunState.FAILED, "wall_time_exceeded", {"reason": "wall_time_exceeded"}
        if code is None:
            return RunState.FAILED, "sandbox_error", {"reason": "no exit status"}
        if code != 0:
            if code == KILLED_EXIT and SandboxEventKind.LIMIT_HIT not in events.seen:
                # Exit 137 is SIGKILL: what the memory limit does to a process (seen on a live 0.1.2 gateway, which reported no
                # event of its own). It can also be an outside kill, so the row says where the word comes from.
                events.add(SandboxEvent(SandboxEventKind.LIMIT_HIT, datetime.now(timezone.utc), {
                    "limit": "memory", "value": self._config.limits.memory, "source": "exit_code",
                    "message": "the process was killed (exit 137), which is what the memory limit does",
                }))
            return RunState.FAILED, f"sandbox_exit_{code}", {"code": code}
        output = _last_json_line(bytes(out))
        if output is None or "result" not in output:
            return RunState.FAILED, "bad_output", {"code": code, "reason": "bad_output"}
        entry.output = output["result"]
        if launch.command[-1] == "check":
            _record_probe_events(events, entry.output)
        return RunState.SUCCEEDED, None, {"code": code}

    async def _finish(
        self, entry: _Entry, spec: RunSpec, events: "_Batcher", token: str | None, state: RunState, error: str | None,
        exit_detail: dict[str, Any],
    ) -> None:
        """Always runs: the exit event, the token, the sandbox, then the status. Each step is allowed to fail alone."""
        execution_id = entry.status.execution_id
        try:
            events.add(SandboxEvent(SandboxEventKind.EXIT, datetime.now(timezone.utc), exit_detail))
            await events.flush()
        except Exception:
            logger.error("run %s: sandbox events not written", execution_id, exc_info=True)
        try:
            if token is not None:
                await revoke_run_tokens(self._pool, spec.tenant_id, execution_id)
        except Exception:
            logger.error("run %s: run token not revoked (it expires by itself)", execution_id, exc_info=True)
        try:
            await self._driver.destroy(str(execution_id))
        except Exception:
            logger.error("run %s: sandbox not destroyed", execution_id, exc_info=True)
        entry.status = dataclasses.replace(entry.status, state=state, finished_at=datetime.now(timezone.utc), error=error)
        entry.done.set()

    # ------------------------------------------------------------------ the rest of the port

    def _entry(self, run_id: str) -> _Entry:
        entry = self._runs.get(run_id)
        if entry is None:
            raise RunNotFound(run_id)
        return entry

    def _evict(self) -> None:
        for run_id in list(self._runs):
            if len(self._runs) <= self._max_tracked:
                break
            if self._runs[run_id].status.state.terminal:
                del self._runs[run_id]

    async def status(self, run_id: str) -> RunStatus:
        return self._entry(run_id).status

    async def wait(self, run_id: str) -> RunResult:
        entry = self._entry(run_id)
        await entry.done.wait()
        return RunResult(status=entry.status, output=entry.output)

    async def stop(self, run_id: str) -> RunStatus:
        entry = self._entry(run_id)
        if entry.task is not None and not entry.status.state.terminal:
            entry.task.cancel()
            await asyncio.wait([entry.task])
            if not entry.done.is_set():  # cancelled before the task ran its first step
                try:
                    await self._driver.destroy(run_id)
                except Exception:
                    logger.error("run %s: sandbox not destroyed", run_id, exc_info=True)
                entry.status = dataclasses.replace(entry.status, state=RunState.STOPPED, finished_at=datetime.now(timezone.utc))
                entry.done.set()
        return entry.status

    async def cleanup(self, run_id: str) -> None:
        entry = self._entry(run_id)
        await self.stop(run_id)
        entry.output = None
        entry.task = None


# ---------------------------------------------------------------------------------------------- helpers

def _record_probe_events(events: "_Batcher", report: Any) -> None:
    """The check probe's own report, as events, for what the stream did not carry. OpenShell logs a refused connection but
    not a refused file read (Landlock only returns EACCES), so without this A4 would leave no event. These rows say
    `source: agent_check`: they are the probe's word, not the sandbox's."""
    if not isinstance(report, dict):
        return
    now = datetime.now(timezone.utc)
    if str(report.get("provider_call", "")).startswith("failed") and SandboxEventKind.NETWORK_DENIED not in events.seen:
        events.add(SandboxEvent(SandboxEventKind.NETWORK_DENIED, now, {
            "host": "api.openai.com", "port": 443, "reason": "agent_check",
        }))
    if str(report.get("outside_read", "")).startswith("failed (PermissionError") and SandboxEventKind.FILE_DENIED not in events.seen:
        events.add(SandboxEvent(SandboxEventKind.FILE_DENIED, now, {
            "path": str(report.get("outside_path", "")), "source": "agent_check", "message": "the read outside the work directory was refused",
        }))


def _is_loud(event: SandboxEvent) -> bool:
    """Denials and limits are written at once, so the Agent runs page shows them while the run is still going."""
    return event.kind not in (SandboxEventKind.LOG, SandboxEventKind.START)


def _last_json_line(data: bytes) -> dict[str, Any] | None:
    for line in reversed(data.decode("utf-8", errors="replace").splitlines()):
        if line.strip():
            try:
                parsed = json.loads(line)
            except ValueError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


class _Batcher:
    """Collects the events of one run and writes them in batches. At most `MAX_EVENTS_PER_RUN` are kept; the rest is one note."""

    def __init__(self, writer: SandboxEventWriter, execution_id: UUID) -> None:
        self._writer = writer
        self._execution_id = execution_id
        self._rows: list[EventRow] = []
        self._seen = 0
        self.seen: set[SandboxEventKind] = set()  # the kinds added so far
        self._truncated = False
        self._last_flush = time.monotonic()

    def add(self, event: SandboxEvent, secrets: tuple[str | None, ...] = ()) -> None:
        if self._seen >= MAX_EVENTS_PER_RUN and event.kind not in (SandboxEventKind.EXIT, SandboxEventKind.LIMIT_HIT):
            if not self._truncated:
                self._truncated = True
                self._rows.append(EventRow(SandboxEventKind.LOG, datetime.now(timezone.utc), {"message": "further events were not kept"}))
            return
        self._seen += 1
        self.seen.add(event.kind)
        self._rows.append(to_row(event, [s for s in secrets if s]))

    async def flush(self) -> None:
        rows, self._rows = self._rows, []
        self._last_flush = time.monotonic()
        try:
            await self._writer.write(rows)
        except Exception:
            # Events are what the sandbox reported, not the control record: a lost batch is logged, never a failed run.
            logger.error("run %s: a batch of sandbox events was not written", self._execution_id, exc_info=True)

    async def flush_if_due(self) -> None:
        if len(self._rows) >= BATCH_SIZE or (self._rows and time.monotonic() - self._last_flush >= FLUSH_SECONDS):
            await self.flush()

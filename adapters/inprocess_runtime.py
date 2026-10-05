"""The default AgentRuntime: runs each agent run as an asyncio task in this process (ADR-0009).

The work itself is a `Runner` given by the composition root (it wraps the LangGraph agent), so this module
knows nothing about agents. Terminal statuses stay readable in a bounded history after `cleanup`; they do not
survive a restart (workers in Sprint 007 and OpenShell in Sprint 009 plug in behind the same port).
"""
import asyncio
import dataclasses
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ports.runtime import (
    RunHandle,
    Runner,
    RunNotFound,
    RunResult,
    RunSpec,
    RunState,
    RunStatus,
)

logger = logging.getLogger("adapters.runtime")


class _Entry:
    def __init__(self, status: RunStatus) -> None:
        self.status = status
        self.output: Any = None
        self.task: asyncio.Task[None] | None = None
        self.done = asyncio.Event()


class InProcessAgentRuntime:
    def __init__(self, runner: Runner | None = None, max_tracked: int = 1000) -> None:
        self._runner = runner
        self._max_tracked = max_tracked
        self._runs: OrderedDict[str, _Entry] = OrderedDict()

    def set_runner(self, runner: Runner) -> None:
        """The composition root gives the runtime its runner once the agent graph is built."""
        self._runner = runner

    async def start(self, spec: RunSpec) -> RunHandle:
        if self._runner is None:
            raise RuntimeError("the agent runtime has no runner")
        execution_id = spec.execution_id or uuid4()
        spec = dataclasses.replace(spec, execution_id=execution_id)
        run_id = str(execution_id)
        if run_id in self._runs:
            raise ValueError(f"run {run_id} already exists")
        entry = _Entry(RunStatus(
            run_id=run_id, execution_id=execution_id, tenant_id=spec.tenant_id, kind=spec.kind,
            state=RunState.RUNNING, started_at=datetime.now(timezone.utc),
        ))
        self._runs[run_id] = entry
        entry.task = asyncio.create_task(self._execute(entry, spec, self._runner))
        self._evict()
        return RunHandle(run_id=run_id, execution_id=execution_id)

    async def _execute(self, entry: _Entry, spec: RunSpec, runner: Runner) -> None:
        state, error = RunState.SUCCEEDED, None
        try:
            entry.output = await runner(spec)
        except asyncio.CancelledError:
            state = RunState.STOPPED
            raise
        except Exception as exc:
            logger.error("run %s failed: %s", entry.status.run_id, exc, exc_info=True)
            state, error = RunState.FAILED, str(exc)
        finally:
            entry.status = dataclasses.replace(
                entry.status, state=state, finished_at=datetime.now(timezone.utc), error=error,
            )
            entry.done.set()

    def _entry(self, run_id: str) -> _Entry:
        entry = self._runs.get(run_id)
        if entry is None:
            raise RunNotFound(run_id)
        return entry

    def _evict(self) -> None:
        # Keep memory bounded: drop the oldest finished runs beyond the limit.
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
                entry.status = dataclasses.replace(
                    entry.status, state=RunState.STOPPED, finished_at=datetime.now(timezone.utc),
                )
                entry.done.set()
        return entry.status

    async def cleanup(self, run_id: str) -> None:
        entry = self._entry(run_id)
        await self.stop(run_id)
        entry.output = None
        entry.task = None

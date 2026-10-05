"""AgentRuntime port: start, observe, stop and clean up agent runs. Every run has an `execution_id`."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID


class RunState(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def terminal(self) -> bool:
        return self is not RunState.RUNNING


class RunNotFound(KeyError):
    """No run with this id (never started, or no longer tracked)."""


@dataclass(frozen=True)
class RunSpec:
    """What to run. `context` is the request's enforcement context (a boundary that only narrows).

    `execution_id` may be allocated by the caller so decisions recorded before `start` carry it too.
    """

    kind: str
    input: dict[str, Any]
    tenant_id: UUID
    context: Any = None
    execution_id: UUID | None = None


@dataclass(frozen=True)
class RunHandle:
    run_id: str
    execution_id: UUID


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    execution_id: UUID
    tenant_id: UUID
    kind: str
    state: RunState
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    output: Any = field(default=None, repr=False)


class AgentRuntime(Protocol):
    async def start(self, spec: RunSpec) -> RunHandle:
        """Start a run and return its handle. The run's `execution_id` is the one in the spec, or a new one."""
        ...

    async def status(self, run_id: str) -> RunStatus:
        """Raises `RunNotFound`."""
        ...

    async def wait(self, run_id: str) -> RunResult:
        """Wait for the run to end. Raises `RunNotFound`; a stopped or failed run is a result, not an exception."""
        ...

    async def stop(self, run_id: str) -> RunStatus:
        """Stop a running run (also during a tool call). Stopping a finished run changes nothing."""
        ...

    async def cleanup(self, run_id: str) -> None:
        """Release what the run holds. A running run is stopped first. Its terminal status stays readable."""
        ...


# A runner executes the work of one run. The in-process runtime is given one by the composition root.
Runner = Callable[[RunSpec], Awaitable[Any]]

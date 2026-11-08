"""What a job handler receives and what it may return or raise."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from core.database.jobs import JobRow
from core.database.tenant import DbPool
from core.settings import Settings
from gateway import GatewayRuntime
from ports import Adapters, SandboxDriver
from ports.events import CloudEvent
from ports.runtime import AgentRuntime, Runner


class PermanentJobError(Exception):
    """The job cannot succeed however often it runs (a file nobody can parse, a run that crashed). The job ends
    `failed` and is not retried. `code` is the stable `error_code` a client sees; `detail` stays in the row."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class JobOutput:
    """What a handler returns. `result` is stored with the job (JSON). `events` are written to the outbox in the
    same transaction that marks the job succeeded, so they exist if and only if the job finished."""

    result: Any = None
    events: list[CloudEvent] = field(default_factory=list)


@dataclass
class JobContext:
    """The handler's view of its job: the job row as claimed, and a way to report progress."""

    job: JobRow
    pool: DbPool
    worker_id: str

    @property
    def tenant_id(self) -> UUID:
        return self.job.tenant_id

    async def progress(self, done: int, total: int) -> None:
        """Record how far the job is. Cheap and safe to call per batch. Does nothing if the job was taken over."""
        from core.database import jobs
        from core.database.tenant import tenant_connection

        async with tenant_connection(self.pool, self.job.tenant_id) as conn:
            await jobs.set_progress(conn, self.job.id, self.worker_id, done, total)


Handler = Callable[[JobRow, JobContext], Awaitable[Any]]


@dataclass(frozen=True)
class JobHandlerDeps:
    """Dependencies provided by the worker composition root to module handler factories."""

    adapters: Adapters
    pool: DbPool
    gateway_runtime: GatewayRuntime
    settings: Settings
    agent_graph: Any | None
    sandbox_driver: SandboxDriver | None
    build_runtime: Callable[[Runner], AgentRuntime]


JobHandlerFactory = Callable[[JobHandlerDeps], dict[str, Handler]]

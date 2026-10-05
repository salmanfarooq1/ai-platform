"""The queued AgentRuntime: a run is a job in Postgres that a worker executes (ADR-0009, ADR-0011, Sprint 007).

`start` writes a job and returns. A worker (`python -m workers`) claims it, rebuilds the enforcement context from
the payload and runs the agent through the in-process runtime inside the worker. Status, result and stop are
read and written through the same job row, so any process can ask about a run, and a status survives a restart.

The adapter never trusts the caller's tenant: it finds the tenant of a run with the narrow
`jobs_tenant_of_execution` lookup and then reads the row under that tenant's connection, as the app role.
A run id that is not a known execution id is `RunNotFound`. The caller still compares `status.tenant_id` with its
own, as with every runtime.

A run's output is JSON (it is stored in `jobs.result`). The run id is the execution id as text.
"""
import asyncio
import time
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from core.database import jobs
from core.database.jobs import JobRow
from core.database.tenant import DbPool, tenant_connection
from ports.runtime import RunHandle, RunNotFound, RunResult, RunSpec, RunState, RunStatus

DEFAULT_RUN_ATTEMPTS = 2  # an agent run is not retried after it fails, only after its worker disappeared


def state_of(row: JobRow) -> RunState:
    """The run state of a job. A job that was stopped ended `failed` with the error code `stopped`."""
    if row.status == "succeeded":
        return RunState.SUCCEEDED
    if row.status in ("queued", "running"):
        return RunState.RUNNING
    return RunState.STOPPED if row.error_code == jobs.STOPPED else RunState.FAILED


def run_status_of(row: JobRow) -> RunStatus:
    state = state_of(row)
    error = (row.error_detail or row.error_code) if state is RunState.FAILED else None
    return RunStatus(
        run_id=str(row.execution_id), execution_id=row.execution_id or uuid4(), tenant_id=row.tenant_id,
        kind=str(row.payload.get("kind", row.kind)), state=state, started_at=row.started_at or row.created_at,
        finished_at=row.finished_at, error=error,
    )


class JobAgentRuntime:
    def __init__(
        self,
        pool: DbPool,
        *,
        serialize_context: Callable[[Any], dict[str, Any]] | None = None,
        poll_interval: float = 0.1,
        stop_wait_seconds: float = 10.0,
        max_attempts: int = DEFAULT_RUN_ATTEMPTS,
    ) -> None:
        self._pool = pool
        self._serialize = serialize_context
        self._poll = poll_interval
        self._stop_wait = stop_wait_seconds
        self._max_attempts = max_attempts

    async def start(self, spec: RunSpec) -> RunHandle:
        execution_id = spec.execution_id or uuid4()
        context: dict[str, Any] | None = None
        if spec.context is not None:
            spec.context.execution_id = execution_id  # decisions the caller records for this run carry the id
            if self._serialize is None:
                raise RuntimeError("the queued runtime needs a context serializer to carry a context to a worker")
            context = self._serialize(spec.context)
        payload = {"kind": spec.kind, "input": spec.input, "context": context}
        namespace = spec.input.get("namespace")
        who = (context or {}).get("principal") or {}
        # The gateway bounded the question to `max_query_length` characters (up to 4 bytes each): allow that much.
        boundary = (context or {}).get("boundary") or {}
        text_cap = max(jobs.MAX_TEXT_BYTES, 4 * int(boundary.get("max_query_length", 0)))
        async with tenant_connection(self._pool, spec.tenant_id) as conn:
            await jobs.enqueue(
                conn, spec.tenant_id, jobs.KIND_AGENT_RUN, payload, max_attempts=self._max_attempts,
                resource=namespace if isinstance(namespace, str) else None, execution_id=execution_id,
                principal_id=UUID(who["id"]) if who.get("id") else None,
                namespace=namespace if isinstance(namespace, str) else None, max_text_bytes=text_cap,
            )
        return RunHandle(run_id=str(execution_id), execution_id=execution_id)

    async def _locate(self, run_id: str) -> tuple[UUID, UUID]:
        try:
            execution_id = UUID(run_id)
        except ValueError:
            raise RunNotFound(run_id) from None
        tenant = await jobs.execution_tenant(self._pool, execution_id)
        if tenant is None:
            raise RunNotFound(run_id)
        return tenant, execution_id

    async def _row(self, run_id: str) -> JobRow:
        tenant, execution_id = await self._locate(run_id)
        async with tenant_connection(self._pool, tenant) as conn:
            row = await jobs.get_by_execution(conn, execution_id)
        if row is None:
            raise RunNotFound(run_id)
        return row

    async def status(self, run_id: str) -> RunStatus:
        return run_status_of(await self._row(run_id))

    async def wait(self, run_id: str) -> RunResult:
        delay = self._poll
        while True:
            row = await self._row(run_id)
            if row.terminal:
                output = row.result if row.status == "succeeded" else None
                return RunResult(status=run_status_of(row), output=output)
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 0.5)

    async def stop(self, run_id: str) -> RunStatus:
        tenant, execution_id = await self._locate(run_id)
        async with tenant_connection(self._pool, tenant) as conn:
            row = await jobs.get_by_execution(conn, execution_id)
            if row is None:
                raise RunNotFound(run_id)
            if not row.terminal:
                row = await jobs.request_cancel(conn, row.id) or row
        deadline = time.monotonic() + self._stop_wait
        while not row.terminal:
            await asyncio.sleep(min(self._poll, 0.05))
            row = await self._row(run_id)
            if not row.terminal and time.monotonic() > deadline:
                # The worker did not answer: it is gone. End the job here so the run is not left running.
                async with tenant_connection(self._pool, tenant) as conn:
                    row = await jobs.force_stop(conn, row.id) or row
        return run_status_of(row)

    async def cleanup(self, run_id: str) -> None:
        await self.stop(run_id)
        row = await self._row(run_id)
        async with tenant_connection(self._pool, row.tenant_id) as conn:
            await jobs.clear_result(conn, row.id)

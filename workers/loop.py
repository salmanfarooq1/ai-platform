"""The worker loop: claim a job, run its handler under a lease, and write the outcome (ADR-0011).

Each slot repeats: claim one job (`jobs_claim`, `FOR UPDATE SKIP LOCKED`), open a tenant connection and read the
job, run the handler, and renew the lease every beat while it runs. The same beat reads `cancel_requested` and
stops the handler when somebody asked. The outcome is written under `tenant_connection`, as the app role:
- the handler returned: `succeeded`, with its result and its events in the outbox, in one transaction;
- a `PermanentJobError`: `failed`, no retry;
- any other error: back to `queued` after a backoff, or `dead` after the last attempt;
- the worker is shutting down and the job did not end within the grace time: the lease is released.

A worker that dies (kill -9) writes nothing. Its lease runs out and `jobs_claim` hands the job to another worker.
A worker that lost its lease (it was too slow to renew) stops its handler and writes nothing: the job is not its
own any more, and every write is guarded by `locked_by`.
"""
import asyncio
import contextlib
import logging
import os
import socket
import time
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID, uuid4

from core.database import jobs
from core.database.jobs import JobRow
from core.database.tenant import DbPool, tenant_connection
from ports.events import EventBus
from workers.types import Handler, JobContext, JobOutput, PermanentJobError

logger = logging.getLogger("workers.loop")


class Worker:
    def __init__(
        self,
        pool: DbPool,
        handlers: Mapping[str, Handler],
        *,
        events: EventBus | None = None,
        name: str | None = None,
        lease_seconds: int = 60,
        poll_interval: float = 0.5,
        backoff_base: float = 2.0,
        beat_interval: float = 1.0,
        shutdown_grace: float = 30.0,
        health_file: str | Path | None = None,
    ) -> None:
        self._pool = pool
        self._handlers = dict(handlers)
        self._events = events
        self._name = name or f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:6]}"
        self._lease = lease_seconds
        self._poll = poll_interval
        self._backoff = backoff_base
        self._beat = min(beat_interval, max(lease_seconds / 3, 0.05))
        self._grace = shutdown_grace
        self._health_file = Path(health_file) if health_file else None
        self._stopping = asyncio.Event()
        self._stopped_at: float | None = None
        self.completed = 0  # jobs this worker finished (any outcome), for tests and the log line

    # ------------------------------------------------------------------ lifecycle

    def stop(self) -> None:
        """Stop claiming. A job in flight gets `shutdown_grace` seconds to end, then its lease is released."""
        if not self._stopping.is_set():
            self._stopped_at = time.monotonic()
            self._stopping.set()

    async def run(self, concurrency: int = 1) -> None:
        """Run `concurrency` slots until `stop()`. Returns when every slot has ended."""
        slots = [asyncio.create_task(self._slot(f"{self._name}/{i}")) for i in range(concurrency)]
        health = asyncio.create_task(self._health_loop()) if self._health_file else None
        logger.info("worker %s started: concurrency=%d lease=%ds", self._name, concurrency, self._lease)
        try:
            await asyncio.gather(*slots)
        finally:
            for task in slots:
                task.cancel()
            if health:
                health.cancel()
            await asyncio.gather(*slots, *([health] if health else []), return_exceptions=True)
            logger.info("worker %s stopped: finished=%d", self._name, self.completed)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), seconds)

    async def _health_loop(self) -> None:
        assert self._health_file is not None
        while True:
            try:
                tmp = self._health_file.with_suffix(".tmp")
                tmp.write_text(str(time.time()))
                os.replace(tmp, self._health_file)
            except OSError:
                logger.warning("worker health file not written: %s", self._health_file, exc_info=True)
            await asyncio.sleep(5.0)

    # ------------------------------------------------------------------ one slot

    async def _slot(self, slot_id: str) -> None:
        while not self._stopping.is_set():
            try:
                claimed = await jobs.claim(self._pool, slot_id, self._lease, tuple(sorted(self._handlers)))
            except Exception:
                logger.error("job claim failed, retrying", exc_info=True)
                await self._sleep(max(self._poll, 1.0))
                continue
            if claimed is None:
                await self._sleep(self._poll)
                continue
            try:
                await self._process(slot_id, *claimed)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("job %s: outcome not written, the lease will expire", claimed[0], exc_info=True)

    async def _process(self, slot_id: str, job_id: UUID, tenant_id: UUID) -> None:
        try:
            async with tenant_connection(self._pool, tenant_id) as conn:
                job = await jobs.get(conn, job_id)
        except Exception:
            job = None
            logger.error("job %s claimed but not readable", job_id, exc_info=True)
        if job is None:
            # Do not sit on a job nobody can run until its lease ends: give it back (the attempt is not counted).
            try:
                async with tenant_connection(self._pool, tenant_id) as conn:
                    await jobs.release(conn, job_id, slot_id)
            except Exception:
                logger.error("job %s could not be released, its lease will expire", job_id, exc_info=True)
            return
        handler = self._handlers.get(job.kind)
        if handler is None:
            await self._finish_failed(slot_id, job, "unknown_job_kind", None, retry=False)
            return
        logger.info("job %s claimed: kind=%s attempt=%d/%d", job.id, job.kind, job.attempts, job.max_attempts)
        jctx = JobContext(job=job, pool=self._pool, worker_id=slot_id)

        async def call() -> object:
            return await handler(job, jctx)

        run: asyncio.Task[object] = asyncio.create_task(call())
        why: list[str] = []
        beat = asyncio.create_task(self._heartbeat(slot_id, job, run, why))
        try:
            await asyncio.wait({run})
        except asyncio.CancelledError:
            # The slot itself was cancelled (a hard stop): drop the handler and write nothing, like a crash.
            run.cancel()
            beat.cancel()
            raise
        finally:
            beat.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await beat
        self.completed += 1
        if run.cancelled():
            reason = why[0] if why else "cancelled"
            if reason == "shutdown":
                async with tenant_connection(self._pool, tenant_id) as conn:
                    await jobs.release(conn, job.id, slot_id)
                logger.info("job %s released for shutdown", job.id)
            elif reason == "cancel":
                await self._finish_failed(slot_id, job, jobs.STOPPED, None, retry=False)
            else:  # lease lost: the job belongs to another worker now
                logger.warning("job %s: lease lost, outcome not written", job.id)
            return
        error = run.exception()
        if error is None:
            await self._finish_ok(slot_id, job, run.result())
        elif isinstance(error, PermanentJobError):
            await self._finish_failed(slot_id, job, error.code, error.detail, retry=False)
        else:
            logger.error("job %s failed: %s", job.id, type(error).__name__, exc_info=error)
            await self._finish_failed(slot_id, job, "internal_error", type(error).__name__, retry=True)

    async def _heartbeat(self, slot_id: str, job: JobRow, run: asyncio.Task[object], why: list[str]) -> None:
        while not run.done():
            await asyncio.sleep(self._beat)
            try:
                async with tenant_connection(self._pool, job.tenant_id) as conn:
                    held, cancel = await jobs.heartbeat(conn, job.id, slot_id, self._lease)
            except Exception:
                logger.warning("job %s: heartbeat failed, will try again", job.id, exc_info=True)
                continue
            if not held:
                why.append("lease")
            elif cancel:
                why.append("cancel")
            elif self._stopped_at is not None and time.monotonic() - self._stopped_at >= self._grace:
                why.append("shutdown")
            if why:
                run.cancel()
                return

    # ------------------------------------------------------------------ outcomes

    async def _finish_ok(self, slot_id: str, job: JobRow, output: object) -> None:
        events = output.events if isinstance(output, JobOutput) else []
        result = output.result if isinstance(output, JobOutput) else output
        try:
            async with tenant_connection(self._pool, job.tenant_id) as conn:
                if not await jobs.complete(conn, job.id, slot_id, result):
                    logger.warning("job %s: finished but no longer held, result dropped", job.id)
                    return
                for event in events:
                    if self._events is None:
                        raise RuntimeError("a job produced events but the worker has no event bus")
                    await self._events.publish(event, tx=conn)  # the outbox row commits with the job
        except Exception:
            # The state change and its events roll back together. Run the job again rather than lose the event.
            logger.error("job %s: could not record success, retrying", job.id, exc_info=True)
            await self._finish_failed(slot_id, job, "outcome_not_recorded", None, retry=True)
            return
        logger.info("job %s succeeded", job.id)

    async def _finish_failed(self, slot_id: str, job: JobRow, code: str, detail: str | None, *, retry: bool) -> None:
        async with tenant_connection(self._pool, job.tenant_id) as conn:
            status = await jobs.fail(conn, job.id, slot_id, code, detail, retry=retry, backoff_base=self._backoff)
        logger.info("job %s -> %s (%s)", job.id, status, code)

"""Workers and the outbox relay inside the API process, for one-process hosting and for tests.

`EMBEDDED_WORKERS=N` (and `EMBEDDED_RELAY=true`) starts them in the API's lifespan, on the API's pool and ports.
They are the same `Worker` and `OutboxRelay` as `python -m workers`, so a job behaves the same. With several API
processes each one runs its own: the queue is safe for that (`SKIP LOCKED`).
"""
import asyncio
import contextlib
import logging
from typing import Any

from adapters.pg_outbox_events import OutboxRelay
from core.database.tenant import DbPool
from core.settings import Settings
from gateway import GatewayRuntime
from ports import Adapters
from workers.context import build_handlers, make_relay, make_worker
from workers.loop import Worker
from workers.scheduler import run_scheduler

logger = logging.getLogger("workers.embedded")


class EmbeddedWorkers:
    def __init__(
        self, worker: Worker | None, concurrency: int, relay: OutboxRelay | None, relay_interval: float,
        schedule: tuple[DbPool, int, float] | None = None,
    ) -> None:
        self._worker, self._concurrency = worker, concurrency
        self._schedule = schedule  # (pool, default retention days, interval seconds)
        self._stop_scheduler = asyncio.Event()
        self._scheduler_task: asyncio.Task[None] | None = None
        self._relay, self._relay_interval = relay, relay_interval
        self._worker_task: asyncio.Task[None] | None = None
        self._relay_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._worker is not None:
            self._worker_task = asyncio.create_task(self._worker.run(self._concurrency))
        if self._relay is not None:
            self._relay_task = asyncio.create_task(self._relay_loop())
        if self._schedule is not None:
            pool, days, interval = self._schedule
            self._scheduler_task = asyncio.create_task(run_scheduler(pool, days, interval, self._stop_scheduler))

    async def _relay_loop(self) -> None:
        assert self._relay is not None
        while True:
            try:
                await self._relay.run_once()
            except Exception:
                logger.error("outbox relay pass failed", exc_info=True)
            await asyncio.sleep(self._relay_interval)

    async def stop(self) -> None:
        """Idempotent. The relay is cancelled. The worker stops claiming and gets its shutdown grace for a job in flight."""
        self._stop_scheduler.set()
        if self._scheduler_task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._scheduler_task
        if self._relay_task is not None:
            self._relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._relay_task
        if self._worker is not None and self._worker_task is not None:
            self._worker.stop()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._worker_task


def start_embedded(
    settings: Settings, pool: DbPool, adapters: Adapters, gateway_runtime: GatewayRuntime, agent_graph: Any,
    *, workers: int, relay: bool, keyring: Any = None,
) -> EmbeddedWorkers:
    worker = None
    if workers > 0:
        handlers = build_handlers(adapters, pool, gateway_runtime, agent_graph, settings, keyring)
        worker = make_worker(settings, pool, handlers, adapters.events, name="embedded", shutdown_grace=5.0)
    relay_obj, relay_cfg = make_relay(settings, pool) if relay else (None, None)
    interval = settings.retention_schedule_interval_seconds
    schedule = (pool, settings.decision_retention_days, interval) if workers > 0 and interval > 0 else None
    embedded = EmbeddedWorkers(worker, workers, relay_obj, relay_cfg.interval if relay_cfg else 1.0, schedule)
    embedded.start()
    return embedded

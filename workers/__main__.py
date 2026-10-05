"""`python -m workers [--concurrency N] [--no-relay]`: claim jobs, run them, and relay the outbox.

SIGTERM and SIGINT stop it gracefully: it stops claiming, lets the jobs in flight finish for
`WORKER_SHUTDOWN_GRACE_SECONDS`, then gives their leases back and exits. It writes the file `WORKER_HEALTH_FILE`
every few seconds (the compose health check reads its age) and logs one line per job.
"""
import argparse
import asyncio
import logging
import signal
import sys

from adapters.registry import build_adapters
from api.observability import setup_logging
from core.database.pool import create_pool
from core.settings import get_settings
from gateway import GatewayRuntime
from workers.context import build_handlers, make_relay, make_worker

logger = logging.getLogger("workers")


async def main(concurrency: int | None, relay_enabled: bool) -> int:
    settings = get_settings()
    slots = concurrency or settings.worker_concurrency
    pool = await create_pool()
    adapters = build_adapters(settings, pool=pool)
    gateway_runtime = GatewayRuntime(pool=pool, cache=adapters.cache, events=adapters.events)
    await adapters.cache.ensure_semantic_index()
    handlers = build_handlers(adapters, pool, gateway_runtime)
    worker = make_worker(settings, pool, handlers, adapters.events, health_file=settings.worker_health_file)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)

    relay_task = None
    if relay_enabled:
        relay, cfg = make_relay(settings, pool)

        async def relay_loop() -> None:
            while True:
                try:
                    await relay.run_once()
                except Exception:
                    logger.error("outbox relay pass failed", exc_info=True)
                await asyncio.sleep(cfg.interval)

        relay_task = asyncio.create_task(relay_loop())
    try:
        await worker.run(slots)
    finally:
        if relay_task is not None:
            relay_task.cancel()
            await asyncio.gather(relay_task, return_exceptions=True)
        await adapters.cache.close()
        await pool.close()
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(prog="python -m workers", description=__doc__)
    parser.add_argument("--concurrency", type=int, default=None, help="jobs run at once (default: WORKER_CONCURRENCY)")
    parser.add_argument("--no-relay", action="store_true", help="do not relay the outbox from this process")
    args = parser.parse_args()
    setup_logging()
    return asyncio.run(main(args.concurrency, not args.no_relay))


if __name__ == "__main__":
    sys.exit(cli())

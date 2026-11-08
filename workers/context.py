"""Build what a worker process needs: the ports and the enabled job handlers.

`python -m workers` and the embedded workers of the API both come through here, so a job runs the same code
wherever it is claimed. The worker does not serve requests: it has no auth middleware, and it acts for a request
only through the enforcement context a job carries.
"""
import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from adapters.inprocess_events import InProcessEventBus
from adapters.kafka_event_bus import build_kafka_bus
from adapters.local_runtime import build_local_runtime
from adapters.pg_outbox_events import OutboxRelay
from core.database.jobs import KIND_INGEST, KIND_PURGE
from core.database.tenant import DbPool
from core.modules import MODULES
from core.settings import Settings, get_settings
from evidence.receipts import Keyring, keyring_from_settings
from gateway import GatewayRuntime
from ports import Adapters, EventBus, SandboxDriver
from workers.handlers.purge import make_purge_handler
from workers.loop import Worker
from workers.types import Handler, JobHandlerDeps


def build_handlers(
    adapters: Adapters, pool: DbPool, gateway_runtime: GatewayRuntime, agent_graph: Any | None = None,
    settings: Settings | None = None, keyring: Keyring | None = None, sandbox_driver: SandboxDriver | None = None,
) -> dict[str, Handler]:
    """Build platform handlers and those registered by the enabled modules."""
    active = settings if settings is not None else get_settings()
    active_keyring = keyring if keyring is not None else keyring_from_settings(active)
    handlers: dict[str, Handler] = {
        KIND_PURGE: make_purge_handler(
            adapters.events, active.decision_retention_days, active.purge_batch_size,
            active_keyring.sign,
        ),
        KIND_INGEST: _make_ingest_handler(adapters),
    }
    deps = JobHandlerDeps(
        adapters=adapters,
        pool=pool,
        gateway_runtime=gateway_runtime,
        settings=active,
        agent_graph=agent_graph,
        sandbox_driver=sandbox_driver,
        build_runtime=lambda runner: build_local_runtime(
            active, runner=runner, pool=pool, sandbox_driver=sandbox_driver,
        ),
    )
    for module in MODULES:
        if module.name not in active.enabled_module_names:
            continue
        for path in module.job_handlers:
            module_path, separator, factory_name = path.partition(":")
            if not separator or not module_path or not factory_name:
                raise RuntimeError(f"invalid job handler path for module {module.name}: {path}")
            factory = getattr(importlib.import_module(module_path), factory_name)
            module_handlers = factory(deps)
            for kind, handler in module_handlers.items():
                if kind in handlers:
                    raise RuntimeError(f"job handler kind {kind!r} is registered more than once")
                handlers[kind] = handler
    return handlers


def _make_ingest_handler(adapters: Adapters) -> Handler:
    from workers.handlers.ingest import make_ingest_handler

    return make_ingest_handler(adapters.knowledge, adapters.embeddings, adapters.objects)


def make_worker(
    settings: Settings, pool: DbPool, handlers: Mapping[str, Handler], events: EventBus, *,
    name: str | None = None, health_file: str | None = None, shutdown_grace: float | None = None,
) -> Worker:
    return Worker(
        pool, handlers, events=events, name=name, lease_seconds=settings.job_lease_seconds,
        poll_interval=settings.job_poll_interval_seconds, beat_interval=settings.job_beat_interval_seconds,
        backoff_base=settings.job_backoff_base_seconds,
        shutdown_grace=settings.worker_shutdown_grace_seconds if shutdown_grace is None else shutdown_grace,
        health_file=health_file,
    )


@dataclass
class RelaySettings:
    interval: float
    batch: int
    max_attempts: int


def make_relay(settings: Settings, pool: DbPool, target: EventBus | None = None) -> tuple[OutboxRelay, RelaySettings]:
    """The relay publishes to `target`: Kafka when EVENT_BUS=kafka, the in-process bus otherwise."""
    if target is None:
        target = build_kafka_bus(settings, pool) if settings.event_bus == "kafka" else InProcessEventBus()
    relay = OutboxRelay(
        pool, target, batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
    )
    return relay, RelaySettings(settings.outbox_poll_interval_seconds, settings.outbox_batch_size, settings.outbox_max_attempts)

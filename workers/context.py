"""Build what a worker process needs: the pool, the ports, the agent graph, and the job handlers.

`python -m workers` and the embedded workers of the API both come through here, so a job runs the same code
wherever it is claimed. The worker does not serve requests: it has no auth middleware, and it acts for a request
only through the enforcement context a job carries.
"""
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from adapters.inprocess_events import InProcessEventBus
from adapters.pg_outbox_events import OutboxRelay
from adapters.registry import build_local_runtime
from api.agent.graph import build_agent_graph
from api.agent.response import book_agent_usage, build_agent_result, build_sandbox_result
from api.agent.runner import AgentRunOutput, make_agent_runner
from core.database.jobs import KIND_AGENT_RUN, KIND_INGEST, KIND_PURGE
from core.database.tenant import DbPool
from core.settings import Settings, get_settings
from gateway import EnforcementContext, GatewayRuntime
from gateway.receipts import Keyring, keyring_from_settings
from ports import Adapters, EventBus, RunSpec, SandboxDriver
from workers.handlers.agent_run import make_agent_run_handler
from workers.handlers.ingest import make_ingest_handler
from workers.handlers.purge import make_purge_handler
from workers.loop import Worker
from workers.types import Handler, JobContext, PermanentJobError

logger = logging.getLogger("workers.context")


def _since_claim(jctx: JobContext) -> float:
    """Seconds since the job was first picked up, so the answer's time covers the run and not the queue."""
    started = jctx.job.started_at or jctx.job.created_at
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


async def _finish_agent_run(spec: RunSpec, output: Any, ctx: EnforcementContext | None, jctx: JobContext) -> dict[str, Any]:
    """The stored result of an agent run: the response, and the usage booked once, here, where the run ended."""
    if isinstance(output, dict):
        # A sandboxed run (Sprint 009). The model calls were booked by the gateway as the agent made them, so nothing is booked here.
        try:
            return build_sandbox_result(
                output, str(spec.input["question"]), str(spec.input.get("namespace", "default")), _since_claim(jctx),
            )
        except ValidationError:
            logger.error("run %s: the sandbox output did not fit the output model", spec.execution_id)
            raise PermanentJobError("sandbox_output_invalid") from None
    if not isinstance(output, AgentRunOutput):
        raise TypeError("an agent run returned something other than AgentRunOutput")
    result = build_agent_result(
        output, str(spec.input["question"]), str(spec.input.get("namespace", "default")), ctx, _since_claim(jctx),
    )
    usage = result["usage"]
    if usage is not None and ctx is not None:
        usage["budget_headers"] = await book_agent_usage(
            jctx.pool, ctx.runtime, spec.tenant_id, ctx.request_id, usage, spec.execution_id,
        )
        usage["booked"] = True
    return result


def build_handlers(
    adapters: Adapters, pool: DbPool, gateway_runtime: GatewayRuntime, agent_graph: Any | None = None,
    settings: Settings | None = None, keyring: Keyring | None = None, sandbox_driver: SandboxDriver | None = None,
) -> dict[str, Handler]:
    """The handler of every job kind. The agent runs on a runtime of its own inside this process."""
    active = settings if settings is not None else get_settings()
    graph = agent_graph if agent_graph is not None else build_agent_graph(adapters)
    local = build_local_runtime(active, runner=make_agent_runner(lambda: graph), pool=pool, sandbox_driver=sandbox_driver)
    return {
        KIND_INGEST: make_ingest_handler(adapters.knowledge, adapters.embeddings, adapters.objects),
        KIND_AGENT_RUN: make_agent_run_handler(local, gateway_runtime, _finish_agent_run),
        KIND_PURGE: make_purge_handler(
            adapters.events, active.decision_retention_days, active.purge_batch_size,
            (keyring if keyring is not None else keyring_from_settings(active)).sign,
        ),
    }


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
    """The relay publishes to `target`, the in-process bus by default (the Kafka adapter takes its place in 010)."""
    relay = OutboxRelay(
        pool, target if target is not None else InProcessEventBus(), batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
    )
    return relay, RelaySettings(settings.outbox_poll_interval_seconds, settings.outbox_batch_size, settings.outbox_max_attempts)

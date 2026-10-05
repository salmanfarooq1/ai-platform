"""The `agent_run` job: run the agent for a request that was accepted, through the AgentRuntime (ADR-0009).

The payload carries the run's input and the request's enforcement context (who, the fixed boundary, the request
id). The handler rebuilds the context, starts the run on the worker's own in-process runtime (the port, not the
graph), and waits. Every decision the run causes carries the `execution_id` of the job. `finish` turns the run's
output into the JSON result stored with the job. If the job is cancelled while the run is inside a tool call, the
handler's cancellation stops the run too.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.database.jobs import JobRow
from gateway import EnforcementContext, GatewayRuntime
from gateway.context import context_from_payload
from ports import AgentRuntime, RunSpec, RunState
from workers.types import Handler, JobContext, PermanentJobError

logger = logging.getLogger("workers.agent_run")

# Turns a run's raw output into the JSON that is stored. Gets the spec and the rebuilt context (None if there was none).
Finish = Callable[[RunSpec, Any, EnforcementContext | None, JobContext], Awaitable[Any]]


async def keep_output(spec: RunSpec, output: Any, ctx: EnforcementContext | None, jctx: JobContext) -> Any:
    return output


def make_agent_run_handler(local: AgentRuntime, gateway_runtime: GatewayRuntime, finish: Finish = keep_output) -> Handler:
    async def handle(job: JobRow, jctx: JobContext) -> Any:
        payload = job.payload
        raw_context = payload.get("context")
        ctx = context_from_payload(gateway_runtime, raw_context) if raw_context else None
        spec = RunSpec(
            kind=payload["kind"], input=payload["input"], tenant_id=job.tenant_id, context=ctx,
            execution_id=job.execution_id,
        )
        handle_ = await local.start(spec)
        try:
            outcome = await local.wait(handle_.run_id)
        except asyncio.CancelledError:
            await local.cleanup(handle_.run_id)  # stops the run, also inside a tool call
            raise
        await local.cleanup(handle_.run_id)
        if outcome.status.state is RunState.SUCCEEDED:
            return await finish(spec, outcome.output, ctx, jctx)
        logger.error("run %s ended %s: %s", handle_.run_id, outcome.status.state.value, outcome.status.error)
        raise PermanentJobError("agent_run_failed")  # the text stays in the log, not in the job row

    return handle

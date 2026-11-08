"""Composition for the agent job handler, loaded only when the Agents module is enabled."""
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from core.database.jobs import KIND_AGENT_RUN
from gateway import EnforcementContext
from ports import RunSpec
from workers.handlers.agent_run import make_agent_run_handler
from workers.types import Handler, JobContext, JobHandlerDeps, PermanentJobError

logger = logging.getLogger("workers.agent_jobs")


def _since_claim(jctx: JobContext) -> float:
    """Seconds since the job was first picked up, so the answer's time covers the run and not the queue."""
    started = jctx.job.started_at or jctx.job.created_at
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


async def _finish_agent_run(
    spec: RunSpec, output: Any, ctx: EnforcementContext | None, jctx: JobContext,
) -> dict[str, Any]:
    """Build and book the stored result where the agent run ends."""
    from api.agent.response import book_agent_usage, build_agent_result, build_sandbox_result
    from api.agent.runner import AgentRunOutput

    if isinstance(output, dict):
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


def build_agent_job_handlers(deps: JobHandlerDeps) -> dict[str, Handler]:
    """Build the handler map for agent runs. This module is imported only for an enabled Agents module."""
    from api.agent.graph import build_agent_graph
    from api.agent.runner import make_agent_runner

    graph = deps.agent_graph if deps.agent_graph is not None else build_agent_graph(deps.adapters)
    runtime = deps.build_runtime(make_agent_runner(lambda: graph))
    return {KIND_AGENT_RUN: make_agent_run_handler(runtime, deps.gateway_runtime, _finish_agent_run)}

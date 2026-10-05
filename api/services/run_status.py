"""Run status for the console: the AgentRuntime's view of an agent run, for the caller's own tenant only."""
from uuid import UUID

from api.models.console import DecisionSummary
from gateway import ActionKind
from ports import AgentRuntime, RunNotFound


async def with_run_status(runtime: AgentRuntime, owner: UUID, items: list[DecisionSummary]) -> list[DecisionSummary]:
    """Fill `run_status` on the `agent.run` decisions from the runtime. A run of another tenant, or one the
    runtime no longer tracks (or never started), gets None."""
    for item in items:
        if item.action != ActionKind.AGENT_RUN.value or item.execution_id is None:
            continue
        try:
            status = await runtime.status(str(item.execution_id))
        except RunNotFound:
            continue
        if status.tenant_id == owner:
            item.run_status = status.state.value
    return items

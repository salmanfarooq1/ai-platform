"""Run status for the console: the state of an agent run, read from its job (durable, Sprint 007).

The status is read under the caller's own tenant connection, so row-level security hides the runs of other tenants
(a decision that names a foreign execution id gets no status). A run that never started (denied at the entry) has
no job and gets None.
"""
from uuid import UUID

from api.models.console import DecisionSummary
from core.database import jobs
from core.database.tenant import DbPool, tenant_connection
from gateway import ActionKind


def run_status_word(status: str, error_code: str | None) -> str:
    """`queued`, `running`, `succeeded`, `failed` or `stopped`. A `dead` job is a failed run."""
    if status in ("queued", "running", "succeeded"):
        return status
    return "stopped" if error_code == jobs.STOPPED else "failed"


async def with_run_status(pool: DbPool, owner: UUID, items: list[DecisionSummary]) -> list[DecisionSummary]:
    """Fill `run_status` on the `agent.run` decisions from the run's job."""
    wanted = {i.execution_id for i in items if i.action == ActionKind.AGENT_RUN.value and i.execution_id is not None}
    if not wanted:
        return items
    async with tenant_connection(pool, owner) as conn:
        rows = await conn.fetch(
            "SELECT execution_id, status, error_code FROM jobs WHERE execution_id = ANY($1::uuid[])", list(wanted),
        )
    by_run = {r["execution_id"]: run_status_word(r["status"], r["error_code"]) for r in rows}
    for item in items:
        if item.action == ActionKind.AGENT_RUN.value and item.execution_id in by_run:
            item.run_status = by_run[item.execution_id]
    return items

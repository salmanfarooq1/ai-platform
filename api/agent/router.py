import asyncio
import logging
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from api.agent.models import AGENT_MAX_TOKENS
from api.agent.response import build_agent_result, combine_usage
from api.agent.runner import AGENT_RUN_KIND, AgentRunOutput
from api.agent.schemas import (
    AgentAccepted,
    AgentCitation,  # noqa: F401 - part of this module's public surface
    AgentQueryResponse,
    AgentRequest,
    AgentResponse,
    AgentRun,
    AgentRunPage,
)
from api.auth import require_any_scope, require_kb, require_scope
from api.dependencies import adapters_of
from api.gateway_deps import entry_action, gateway_context
from api.services.cursor import InvalidCursor, decode_cursor, encode_cursor
from api.services.run_status import run_status_word
from config import LLM_CONFIG
from core.database import jobs as job_store
from core.database.jobs import JobRow
from core.database.tenant import tenant_connection
from core.identity.models import Principal, Scope
from core.settings import get_settings
from gateway import Action, ActionKind, EnforcementContext, require
from gateway.estimate import estimate_tokens
from ports import RunSpec, RunState

logger = logging.getLogger("api.agent")
router = APIRouter(prefix="/agent", tags=["agent"])

# Kept for the code that imported it from here before the move.
_combine_usage = combine_usage


@router.post(
    "/query",
    response_model=AgentResponse,
    responses={202: {"model": AgentAccepted, "description": "The run is still going after the sync wait: poll /v1/agent/runs/{execution_id}"}},
)
async def agent_query(
    request: Request,
    response: Response,
    payload: AgentRequest,
    principal: Principal = Depends(require_scope(Scope.AGENT)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> AgentResponse | JSONResponse:
    start = time.perf_counter()
    adapters = adapters_of(request)
    # The run's id is fixed before the first check, so every decision this request causes carries it.
    execution_id = uuid4()
    ctx.execution_id = execution_id
    # The gateway decides first: scope, input guardrails, rate limit and daily token budget.
    await require(ctx, entry_action(request.url.path, ActionKind.AGENT_RUN, input_text=payload.question))
    await require_kb(adapters.knowledge, principal, payload.namespace)
    # The model must be allowed before the run starts (each LLM call inside the run is checked again).
    await require(ctx, Action(
        ActionKind.MODEL_INVOKE, LLM_CONFIG["model"], estimated_tokens=estimate_tokens(payload.question, AGENT_MAX_TOKENS),
        input_text=payload.question,
    ))

    # The run goes through the AgentRuntime port (ADR-0009): with the queued runtime it is a job a worker runs.
    try:
        handle = await adapters.runtime.start(RunSpec(
            kind=AGENT_RUN_KIND, input=payload.model_dump(), tenant_id=principal.tenant_id, context=ctx,
            execution_id=execution_id,
        ))
    except job_store.PayloadTooLarge:
        raise HTTPException(status_code=413, detail="The question is too long") from None
    wait_seconds = get_settings().agent_sync_wait_seconds
    try:
        outcome = await asyncio.wait_for(adapters.runtime.wait(handle.run_id), timeout=wait_seconds)
    except asyncio.TimeoutError:
        # Still running after the sync wait. The run is not stopped: the caller polls it by execution id.
        async with tenant_connection(request.app.state.db_pool, principal.tenant_id) as conn:
            job = await job_store.get_by_execution(conn, handle.execution_id)
        if job is None:
            raise HTTPException(status_code=500, detail="Agent execution failed: the run was lost") from None
        return JSONResponse(
            status_code=202, content=AgentAccepted(execution_id=handle.execution_id, job_id=job.id).model_dump(mode="json"),
        )
    except asyncio.CancelledError:
        # A client disconnect cancels this handler: stop the run, including the model call it is inside.
        await asyncio.shield(adapters.runtime.cleanup(handle.run_id))
        raise

    if outcome.status.state is not RunState.SUCCEEDED:
        await adapters.runtime.cleanup(handle.run_id)
        logger.error("[agent] run %s ended %s: %s", handle.run_id, outcome.status.state.value, outcome.status.error)
        # No exception text for the caller: the cause is in the worker's log, the code is in the run.
        raise HTTPException(status_code=500, detail="Agent execution failed")

    output = outcome.output
    if isinstance(output, AgentRunOutput):  # the in-process runtime hands back the raw graph state
        result = build_agent_result(output, payload.question, payload.namespace, ctx, time.perf_counter() - start)
        await adapters.runtime.cleanup(handle.run_id)
    else:  # a worker already built and stored the result, and booked the usage
        result = output
    answer = AgentResponse(**{**result["response"], "total_time_seconds": round(time.perf_counter() - start, 3)})
    usage = result.get("usage")
    if usage:
        request.state.usage = usage
        request.state.usage_booked = bool(usage.get("booked"))
        response.headers["X-Cost-USD"] = f"{usage['total_cost']:.6f}"
    return answer


# ---------------------------------------------------------------------------------------------- runs

def _read_action(request: Request, principal: Principal) -> Action:
    """Reading a run is a read, never an `agent.run` (those rows are the runs themselves). Audit readers read
    through `audit.read`; an agent key reads through `kb.read`, which its scope grants."""
    if principal.has_scope(Scope.AUDIT_READ):
        return Action(ActionKind.AUDIT_READ, resource="runs")
    return entry_action(request.url.path, ActionKind.KB_READ)


def _only_own(principal: Principal) -> UUID | None:
    """A caller without `audit:read` sees only the runs it started. An audit reader sees the tenant's runs."""
    return None if principal.has_scope(Scope.AUDIT_READ) else principal.id


def _may_see(ctx: EnforcementContext, principal: Principal, row: JobRow) -> bool:
    """A run is visible when its knowledge base is one the caller's boundary allows, and (without `audit:read`)
    when the caller started it. Everything else is a 404, the same as a run that does not exist."""
    if row.namespace is not None and not ctx.boundary.allows_kb(row.namespace):
        return False
    return _only_own(principal) in (None, row.principal_id)


def run_view(row: JobRow) -> AgentRun:
    word = run_status_word(row.status, row.error_code)
    stored = row.result if row.status == "succeeded" and isinstance(row.result, dict) else None
    return AgentRun(
        execution_id=row.execution_id or row.id, job_id=row.id, status=word,  # type: ignore[arg-type]
        error_code=row.error_code if word in ("failed", "stopped") else None, created_at=row.created_at,
        started_at=row.started_at, finished_at=row.finished_at,
        result=AgentQueryResponse(**stored["response"]) if stored else None,
        decisions_url=f"/v1/decisions?execution_id={row.execution_id}",
    )


@router.get("/runs", response_model=AgentRunPage)
async def list_runs(
    request: Request,
    cursor: str | None = None,
    limit: int = 50,
    principal: Principal = Depends(require_any_scope(Scope.AGENT, Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> AgentRunPage:
    """The tenant's agent runs, newest first, with a keyset cursor."""
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    await require(ctx, _read_action(request, principal))
    after = None
    if cursor is not None:
        try:
            after = decode_cursor(cursor)
        except InvalidCursor:
            raise HTTPException(status_code=400, detail={"error": "invalid_cursor", "reason": "The cursor is not valid"}) from None
    async with tenant_connection(request.app.state.db_pool, principal.tenant_id) as conn:
        rows = await job_store.list_jobs(
            conn, kind=job_store.KIND_AGENT_RUN, kbs=ctx.boundary.visible_kbs(), principal_id=_only_own(principal),
            cursor=after, limit=limit,
        )
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    return AgentRunPage(items=[run_view(r) for r in page], next_cursor=next_cursor)


@router.get("/runs/{execution_id}", response_model=AgentRun)
async def get_run(
    request: Request,
    execution_id: UUID,
    principal: Principal = Depends(require_any_scope(Scope.AGENT, Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> AgentRun:
    """One run: its status, and its answer once it succeeded. It reads the job, so it also works after a restart."""
    await require(ctx, _read_action(request, principal))
    async with tenant_connection(request.app.state.db_pool, principal.tenant_id) as conn:
        row = await job_store.get_by_execution(conn, execution_id)
    if row is None or not _may_see(ctx, principal, row):  # a foreign run and an unknown run look the same: row-level security hides the foreign one
        raise HTTPException(status_code=404, detail="Run not found")
    return run_view(row)

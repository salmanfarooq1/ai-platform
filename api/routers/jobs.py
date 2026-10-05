"""Job reads: one job, and a page of the tenant's jobs.

Both need `kb:read` and go through `enforce()` (a decision row each). The rows are read under
`tenant_connection`, so row-level security hides every other tenant's jobs. A job for a knowledge base the policy
does not allow is hidden too: it is a 404 by id and left out of the page. A foreign job and a missing job give the
same 404.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth import require_scope
from api.gateway_deps import entry_action, gateway_context
from api.models.jobs import Job, JobKind, JobPage, JobProgress, JobStatus
from api.services.cursor import InvalidCursor, decode_cursor, encode_cursor
from core.database import jobs as job_store
from core.database.jobs import JobRow
from core.database.tenant import tenant_connection
from core.identity.models import Principal, Scope
from gateway import ActionKind, EnforcementContext, require

router = APIRouter(tags=["jobs"])


def job_view(row: JobRow) -> Job:
    return Job(
        id=row.id, kind=row.kind, status=row.status, attempts=row.attempts, max_attempts=row.max_attempts,  # type: ignore[arg-type]
        progress=JobProgress(done=row.progress_done, total=row.progress_total), error_code=row.error_code,
        resource=row.resource, execution_id=row.execution_id, created_at=row.created_at, updated_at=row.updated_at,
    )


def job_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Job not found")


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(
    request: Request,
    job_id: UUID,
    principal: Principal = Depends(require_scope(Scope.KB_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> Job:
    """One job of the caller's tenant: its status, attempts and progress."""
    await require(ctx, entry_action(request.url.path, ActionKind.KB_READ))
    async with tenant_connection(request.app.state.db_pool, principal.tenant_id) as conn:
        row = await job_store.get(conn, job_id)
    if row is None or row.kind not in job_store.USER_KINDS or (
        row.namespace is not None and not ctx.boundary.allows_kb(row.namespace)
    ):
        raise job_not_found()
    return job_view(row)


@router.get("/jobs", response_model=JobPage)
async def list_jobs(
    request: Request,
    kind: JobKind | None = None,
    status: JobStatus | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_scope(Scope.KB_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> JobPage:
    """The tenant's jobs, newest first, with a keyset cursor. Filter by `kind` and `status`."""
    await require(ctx, entry_action(request.url.path, ActionKind.KB_READ))
    after = None
    if cursor is not None:
        try:
            after = decode_cursor(cursor)
        except InvalidCursor:
            raise HTTPException(status_code=400, detail={"error": "invalid_cursor", "reason": "The cursor is not valid"}) from None
    async with tenant_connection(request.app.state.db_pool, principal.tenant_id) as conn:
        rows = await job_store.list_jobs(
            conn, kind=kind, status=status, kbs=ctx.boundary.visible_kbs(), cursor=after, limit=limit,
        )
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    return JobPage(items=[job_view(r) for r in page], next_cursor=next_cursor)

"""Response models of the job routes (Sprint 007). Jobs are tenant-scoped and read under row-level security."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

JobKind = Literal["ingest", "agent_run"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "dead"]


class JobProgress(BaseModel):
    done: int
    total: int


class Job(BaseModel):
    id: UUID
    kind: JobKind
    status: JobStatus
    attempts: int
    max_attempts: int
    progress: JobProgress
    # A stable code when the job failed, was stopped or died: `unsupported_file`, `object_missing`,
    # `agent_run_failed`, `stopped`, `lease_expired`, `internal_error`. None otherwise. A retry that is waiting
    # for its backoff keeps the code of the attempt that failed.
    error_code: str | None
    # For `ingest`: `<knowledge base>/<document id>`. For `agent_run`: the knowledge base. None if the job has none.
    resource: str | None
    # The agent run this job is, for `agent_run`; None for `ingest`.
    execution_id: UUID | None
    created_at: datetime
    updated_at: datetime


class JobPage(BaseModel):
    items: list[Job]
    next_cursor: str | None


class JobAccepted(BaseModel):
    """`202` for a new job, `200` when the idempotency key already named one. `status` is the job's status now:
    `queued` for a new job."""
    job_id: UUID
    status: JobStatus = "queued"

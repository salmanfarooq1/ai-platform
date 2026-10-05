"""The job queue on Postgres (ADR-0011): enqueue, claim, lease, finish, cancel and read.

Every function that touches one tenant's jobs takes a connection from `tenant_connection`, so row-level security
applies. The one exception is `claim`: a worker belongs to no tenant, so it calls the SECURITY DEFINER function
`jobs_claim` (migration 0008), which returns only the job's id and tenant. Everything after that runs under
`tenant_connection`, as the app role.

A job is `queued`, then `running` under a lease, then `succeeded`, `failed` (it will not run again) or `dead` (it
used its last attempt). A failed attempt that may be retried goes back to `queued` with a later `run_after`.
"""
import json
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from asyncpg import Connection, Pool, Record

KIND_INGEST = "ingest"
KIND_AGENT_RUN = "agent_run"
KIND_PURGE = "purge_decisions"  # platform maintenance (Sprint 008): not a caller's job, so the job routes do not show it
USER_KINDS = (KIND_INGEST, KIND_AGENT_RUN)
STATUSES = ("queued", "running", "succeeded", "failed", "dead")
TERMINAL = ("succeeded", "failed", "dead")
MAX_TEXT_BYTES = 4096  # no string in a payload is longer: raw bytes go to the object store
ERROR_DETAIL_CHARS = 500
STOPPED = "stopped"  # the error code of a job somebody stopped

_COLUMNS = (
    "id, tenant_id, kind, status, payload, idempotency_key, attempts, max_attempts, run_after, lease_until, "
    "locked_by, progress_done, progress_total, error_code, error_detail, resource, execution_id, result, "
    "cancel_requested, created_at, updated_at, started_at, finished_at, principal_id, namespace"
)


class PayloadTooLarge(ValueError):
    """A payload string is longer than `MAX_TEXT_BYTES`."""


@dataclass(frozen=True)
class JobRow:
    id: UUID
    tenant_id: UUID
    kind: str
    status: str
    payload: dict[str, Any]
    idempotency_key: str | None
    attempts: int
    max_attempts: int
    run_after: datetime
    lease_until: datetime | None
    locked_by: str | None
    progress_done: int
    progress_total: int
    error_code: str | None
    error_detail: str | None
    resource: str | None
    execution_id: UUID | None
    result: Any
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    principal_id: UUID | None
    namespace: str | None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _row(record: Record) -> JobRow:
    values = dict(record)
    values["payload"] = _json(values["payload"]) or {}
    values["result"] = _json(values["result"])
    return JobRow(**values)


def check_payload(value: Any, limit: int = MAX_TEXT_BYTES) -> None:
    """Refuse a payload that carries a long text. Short ids, names and options are fine. `limit` is raised by a
    caller whose input the gateway already bounded (a question may be `max_query_length` characters)."""
    if isinstance(value, str):
        if len(value.encode("utf-8")) > limit:
            raise PayloadTooLarge(f"a job payload string is longer than {limit} bytes")
    elif isinstance(value, dict):
        for item in value.values():
            check_payload(item, limit)
    elif isinstance(value, list):
        for item in value:
            check_payload(item, limit)


def backoff_seconds(base: float, attempts: int, jitter: float = 0.2) -> float:
    """`base * 2^attempts` with up to +-`jitter` of random spread, so retries do not arrive together."""
    delay = base * (2 ** max(attempts, 0))
    return max(0.0, delay * (1 + random.uniform(-jitter, jitter)))


# ---------------------------------------------------------------------------------------------- producers

async def enqueue(
    conn: Connection,
    tenant_id: UUID,
    kind: str,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    max_attempts: int = 5,
    resource: str | None = None,
    execution_id: UUID | None = None,
    principal_id: UUID | None = None,
    namespace: str | None = None,
    max_text_bytes: int = MAX_TEXT_BYTES,
) -> tuple[JobRow, bool]:
    """Insert a job. Returns `(job, created)`. With an idempotency key that the tenant already used, nothing is
    inserted and the first job comes back with `created` False (the unique index decides, so two callers racing
    with one key get one job)."""
    check_payload(payload, max_text_bytes)
    row = await conn.fetchrow(
        f"""
        INSERT INTO jobs (tenant_id, kind, payload, idempotency_key, max_attempts, resource, execution_id,
                          principal_id, namespace)
        VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
        RETURNING {_COLUMNS}
        """,
        tenant_id, kind, json.dumps(payload), idempotency_key, max_attempts, resource, execution_id,
        principal_id, namespace,
    )
    if row is not None:
        return _row(row), True
    existing = await conn.fetchrow(
        f"SELECT {_COLUMNS} FROM jobs WHERE tenant_id = $1 AND idempotency_key = $2", tenant_id, idempotency_key,
    )
    if existing is None:  # the conflicting row is not visible: cannot happen under one tenant's setting
        raise RuntimeError("idempotency conflict without a job")
    return _row(existing), False


# ---------------------------------------------------------------------------------------------- readers

async def get(conn: Connection, job_id: UUID) -> JobRow | None:
    row = await conn.fetchrow(f"SELECT {_COLUMNS} FROM jobs WHERE id = $1", job_id)
    return _row(row) if row else None


async def get_by_execution(conn: Connection, execution_id: UUID) -> JobRow | None:
    row = await conn.fetchrow(f"SELECT {_COLUMNS} FROM jobs WHERE execution_id = $1", execution_id)
    return _row(row) if row else None


async def list_jobs(
    conn: Connection,
    *,
    kind: str | None = None,
    status: str | None = None,
    kbs: list[str] | None = None,
    principal_id: UUID | None = None,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> list[JobRow]:
    """Newest first, keyset paged on `(created_at, id)`. `kbs` limits jobs to those knowledge bases (None means
    all); `principal_id` to the jobs that principal started. Fetches `limit + 1` rows so the caller can tell whether another page exists."""
    conditions: list[str] = []
    args: list[Any] = []

    def add(sql: str, value: Any) -> None:
        args.append(value)
        conditions.append(sql.format(n=len(args)))

    if kind is not None:
        add("kind = ${n}", kind)
    else:
        add("kind = ANY(${n}::text[])", list(USER_KINDS))
    if status is not None:
        add("status = ${n}", status)
    if kbs is not None:
        add("(namespace IS NULL OR namespace = ANY(${n}::text[]))", kbs)
    if principal_id is not None:
        add("principal_id = ${n}", principal_id)
    if cursor is not None:
        args.extend(cursor)
        conditions.append(f"(created_at, id) < (${len(args) - 1}, ${len(args)})")
    args.append(limit + 1)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = await conn.fetch(
        f"SELECT {_COLUMNS} FROM jobs {where} ORDER BY created_at DESC, id DESC LIMIT ${len(args)}", *args,
    )
    return [_row(r) for r in rows]


async def execution_tenant(pool: Pool, execution_id: UUID) -> UUID | None:
    """The tenant of an agent run, from the narrow SECURITY DEFINER lookup. The row itself is then read under
    that tenant's connection."""
    tenant: UUID | None = await pool.fetchval("SELECT jobs_tenant_of_execution($1)", execution_id)
    return tenant


# ---------------------------------------------------------------------------------------------- workers

async def claim(pool: Pool, worker_id: str, lease_seconds: int) -> tuple[UUID, UUID] | None:
    """Claim one job for `lease_seconds`. Returns `(job_id, tenant_id)` or None when nothing is ready. Two workers
    calling at once never get the same job (`FOR UPDATE SKIP LOCKED`)."""
    row = await pool.fetchrow("SELECT claimed_id, claimed_tenant FROM jobs_claim($1, $2)", worker_id, lease_seconds)
    if row is None or row["claimed_id"] is None:
        return None
    return row["claimed_id"], row["claimed_tenant"]


async def heartbeat(conn: Connection, job_id: UUID, worker_id: str, lease_seconds: int) -> tuple[bool, bool]:
    """Extend the lease. Returns `(still_held, cancel_requested)`. `still_held` is False when another worker took
    the job over (the lease had run out) or it is no longer running."""
    row = await conn.fetchrow(
        """
        UPDATE jobs SET lease_until = NOW() + make_interval(secs => $3), updated_at = NOW()
        WHERE id = $1 AND locked_by = $2 AND status = 'running'
        RETURNING cancel_requested
        """,
        job_id, worker_id, lease_seconds,
    )
    return (True, bool(row["cancel_requested"])) if row else (False, False)


async def set_progress(conn: Connection, job_id: UUID, worker_id: str, done: int, total: int) -> bool:
    status = await conn.execute(
        """
        UPDATE jobs SET progress_done = $3, progress_total = $4, updated_at = NOW()
        WHERE id = $1 AND locked_by = $2 AND status = 'running'
        """,
        job_id, worker_id, done, total,
    )
    return status.endswith("1")


async def complete(conn: Connection, job_id: UUID, worker_id: str, result: Any = None) -> bool:
    """Mark a running job succeeded. False when this worker no longer holds it (nothing changes)."""
    status = await conn.execute(
        """
        UPDATE jobs SET status = 'succeeded', result = $3::jsonb, error_code = NULL, error_detail = NULL,
               lease_until = NULL, locked_by = NULL, finished_at = NOW(), updated_at = NOW(),
               payload = payload - 'input'
        WHERE id = $1 AND locked_by = $2 AND status = 'running'
        """,
        job_id, worker_id, json.dumps(result) if result is not None else None,
    )
    return status.endswith("1")


async def fail(
    conn: Connection,
    job_id: UUID,
    worker_id: str,
    error_code: str,
    detail: str | None = None,
    *,
    retry: bool,
    backoff_base: float = 2.0,
) -> str | None:
    """End one attempt. With `retry` the job goes back to `queued` after a backoff, or to `dead` when it used its
    last attempt. Without `retry` it is `failed` for good. Returns the new status, or None when this worker no
    longer holds the job."""
    row = await conn.fetchrow(
        "SELECT attempts, max_attempts FROM jobs WHERE id = $1 AND locked_by = $2 AND status = 'running' FOR UPDATE",
        job_id, worker_id,
    )
    if row is None:
        return None
    attempts, max_attempts = row["attempts"], row["max_attempts"]
    if not retry:
        new_status = "failed"
    elif attempts >= max_attempts:
        new_status = "dead"
    else:
        new_status = "queued"
    delay = backoff_seconds(backoff_base, attempts) if new_status == "queued" else 0.0
    await conn.execute(
        """
        UPDATE jobs SET status = $2, error_code = $3, error_detail = $4, lease_until = NULL, locked_by = NULL,
               run_after = NOW() + make_interval(secs => $5), updated_at = NOW(),
               finished_at = CASE WHEN $2 = 'queued' THEN NULL ELSE NOW() END,
               payload = CASE WHEN $2 = 'queued' THEN payload ELSE payload - 'input' END
        WHERE id = $1
        """,
        job_id, new_status, error_code, (detail or "")[:ERROR_DETAIL_CHARS] or None, delay,
    )
    return new_status


async def release(conn: Connection, job_id: UUID, worker_id: str) -> bool:
    """Give a job back without counting the attempt (a worker that is shutting down)."""
    status = await conn.execute(
        """
        UPDATE jobs SET status = 'queued', lease_until = NULL, locked_by = NULL, attempts = GREATEST(attempts - 1, 0),
               run_after = NOW(), updated_at = NOW()
        WHERE id = $1 AND locked_by = $2 AND status = 'running'
        """,
        job_id, worker_id,
    )
    return status.endswith("1")


# ---------------------------------------------------------------------------------------------- stop

async def request_cancel(conn: Connection, job_id: UUID) -> JobRow | None:
    """Ask for a job to stop. A job that has not started is stopped here and now; a running job gets the flag and
    its worker stops it at its next heartbeat. A finished job is left alone. Returns the row after the change."""
    await conn.execute(
        """
        UPDATE jobs SET status = 'failed', error_code = 'stopped', cancel_requested = TRUE, finished_at = NOW(),
               updated_at = NOW(), payload = payload - 'input'
        WHERE id = $1 AND status = 'queued'
        """,
        job_id,
    )
    await conn.execute(
        "UPDATE jobs SET cancel_requested = TRUE, updated_at = NOW() WHERE id = $1 AND status = 'running'", job_id,
    )
    return await get(conn, job_id)


async def force_stop(conn: Connection, job_id: UUID) -> JobRow | None:
    """End a job whose worker did not answer a stop request in time (it is gone). Used by the runtime's `stop`."""
    await conn.execute(
        """
        UPDATE jobs SET status = 'failed', error_code = 'stopped', cancel_requested = TRUE, lease_until = NULL,
               locked_by = NULL, finished_at = NOW(), updated_at = NOW(), payload = payload - 'input'
        WHERE id = $1 AND status IN ('queued', 'running')
        """,
        job_id,
    )
    return await get(conn, job_id)


async def clear_result(conn: Connection, job_id: UUID) -> None:
    """Release what a finished run holds (its output). The status stays."""
    await conn.execute("UPDATE jobs SET result = NULL, updated_at = NOW() WHERE id = $1 AND status IN ('succeeded', 'failed', 'dead')", job_id)

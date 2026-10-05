"""Helpers for tests that go through the job queue: wait for a job, and read what an ingest job did.

Ingestion answers 202 and a worker does the work. These helpers wait for the job and turn its outcome back
into the answer the synchronous route used to give, so a test about something else (search, tenancy, headers) can
keep its own assertions.
"""
import asyncio
import json
from typing import Any

import asyncpg

OWNER: dict[str, str | None] = {"dsn": None}  # set by the `app` fixture: the owner role, to read across tenants

TERMINAL = ("succeeded", "failed", "dead")


async def job_row(job_id: str) -> asyncpg.Record | None:
    assert OWNER["dsn"], "no owner DSN: the app fixture sets it"
    conn = await asyncpg.connect(OWNER["dsn"], statement_cache_size=0)
    try:
        return await conn.fetchrow("SELECT * FROM jobs WHERE id = $1::uuid", job_id)
    finally:
        await conn.close()


async def wait_for_job(job_id: str, timeout: float = 20.0) -> asyncpg.Record:
    """Wait (reading the table, so no decision rows are written) until the job is succeeded, failed or dead."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        row = await job_row(job_id)
        if row is not None and row["status"] in TERMINAL:
            return row
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"job {job_id} did not finish: {dict(row) if row else None}")
        await asyncio.sleep(0.05)


class IngestOutcome:
    """What the synchronous ingest route used to answer, rebuilt from the finished job."""

    def __init__(self, accepted: Any, status_code: int, body: dict[str, Any], job: asyncpg.Record) -> None:
        self.accepted, self.status_code, self._body, self.job = accepted, status_code, body, job
        self.headers = accepted.headers
        self.text = json.dumps(body)

    def json(self) -> dict[str, Any]:
        return self._body


async def settle(accepted: Any) -> Any:
    """Wait for the job a 202 names and return the old-style answer. Any other response is returned as it is."""
    if accepted.status_code != 202:
        return accepted
    job = await wait_for_job(accepted.json()["job_id"])
    payload = json.loads(job["payload"]) if isinstance(job["payload"], str) else job["payload"]
    if job["status"] == "succeeded":
        result = json.loads(job["result"]) if isinstance(job["result"], str) else job["result"]
        return IngestOutcome(accepted, 200, {
            "document_id": payload["document_id"], "namespace": payload["namespace"], "content_hash": payload["content_hash"],
            "total_chunks": result["total_chunks"], "status": result["status"], "chunks_deleted": result.get("chunks_deleted", 0),
            "total_time_seconds": 0.0, "throughput_chunks_per_second": 0.0,
        }, job)
    request_id = accepted.headers.get("X-Request-ID", "")
    if job["error_code"] == "unsupported_file":
        error = {"code": "unsupported_media_type", "message": "Unsupported or unreadable file", "request_id": request_id}
        return IngestOutcome(accepted, 415, {"error": error}, job)
    return IngestOutcome(accepted, 500, {"error": {"code": "http_500", "message": "Ingestion failed", "request_id": request_id}}, job)


async def post_ingest(client: Any, **kwargs: Any) -> Any:
    """`client.post("/v1/ingest", **kwargs)`, settled."""
    return await settle(await client.post("/v1/ingest", **kwargs))

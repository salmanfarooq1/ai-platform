"""`python -m workers` as a real process: it starts, writes its health file, runs a job it was given, and exits 0 on SIGTERM."""
import asyncio
import os
import signal
import sys
from uuid import UUID

import pytest

from core.database import jobs
from core.database.tenant import tenant_connection
from tests import harness

pytestmark = pytest.mark.asyncio


async def test_the_worker_process_starts_reports_health_and_stops_on_sigterm(db_pool, tenant_a, app_database_url, tmp_path):
    health = tmp_path / "health"
    env = {
        **os.environ, "PYTHONPATH": ".", "MODE": "local", "DATABASE_URL": app_database_url, "REDIS_URL": harness.REDIS_URL,
        "WORKER_HEALTH_FILE": str(health), "JOB_POLL_INTERVAL_SECONDS": "0.1", "OBJECT_STORE_DIR": str(tmp_path / "objects"),
    }
    env.pop("JWT_SECRET", None)
    # a job of a kind with no input it can read: the process claims it and ends it `failed` (object missing)
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        job, _ = await jobs.enqueue(conn, UUID(tenant_a.id), "ingest", {
            "namespace": "legal", "document_id": "a.md", "filename": "a.md", "content_hash": "h", "object_key": "0" * 64})
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "workers", "--concurrency", "2", "--no-relay", env=env,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        for _ in range(300):
            async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
                row = await jobs.get(conn, job.id)
            if health.exists() and row.status == "failed":
                break
            await asyncio.sleep(0.1)
        assert health.exists() and row.status == "failed" and row.error_code == "object_missing"
        proc.send_signal(signal.SIGTERM)
        assert await asyncio.wait_for(proc.wait(), 20) == 0  # a graceful stop, not a kill
    finally:
        if proc.returncode is None:
            proc.kill()

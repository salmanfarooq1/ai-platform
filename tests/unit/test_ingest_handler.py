"""The ingest handler requires a persisted caller before it can do any work."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.database.jobs import JobRow
from core.settings import get_settings
from workers.handlers.ingest import make_ingest_handler
from workers.types import JobContext, PermanentJobError

pytestmark = pytest.mark.unit


async def test_ingest_job_with_no_principal_fails_before_reading_objects():
    class Objects:
        async def get(self, key):
            return b"stored file"

    adapters = SimpleNamespace(
        knowledge=object(), objects=Objects(), embeddings=object(), model_catalog=object(), model_limits=object(),
    )
    settings = get_settings()
    handler = make_ingest_handler(adapters, None, settings)  # type: ignore[arg-type]
    now = datetime.now(timezone.utc)
    job = JobRow(
        id=uuid4(), tenant_id=uuid4(), kind="ingest", status="running", payload={
            "namespace": "legal", "document_id": "doc.md", "content_hash": "hash", "object_key": "object",
        },
        idempotency_key=None, attempts=1, max_attempts=3, run_after=now, lease_until=None, locked_by="worker",
        progress_done=0, progress_total=0, error_code=None, error_detail=None, resource=None, execution_id=None,
        result=None, cancel_requested=False, created_at=now, updated_at=now, started_at=now, finished_at=None,
        principal_id=None, namespace="legal",
    )

    with pytest.raises(PermanentJobError, match="no persisted principal") as caught:
        await handler(job, JobContext(job, object(), "worker"))  # type: ignore[arg-type]
    assert caught.value.code == "principal_missing"

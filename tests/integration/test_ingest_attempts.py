"""WP6: each ingest embedding batch is authorized when the worker runs it."""
from uuid import UUID

import pytest

from core.settings import get_settings
from tests.e2e.test_gateway_e2e import publish
from tests.jobs_helpers import wait_for_job

pytest_plugins = ("tests.e2e.conftest",)


async def _run_queued_ingest(app, job_id: str):
    from workers.embedded import start_embedded

    embedded = start_embedded(
        get_settings(), app.state.db_pool, app.state.adapters, app.state.gateway_runtime,
        app.state.agent_graph, workers=1, relay=False,
    )
    try:
        return await wait_for_job(job_id)
    finally:
        await embedded.stop()


def _three_batch_document() -> bytes:
    return ("Privacy obligations and retention schedules are important. " * 2700).encode()


@pytest.mark.integration
async def test_each_batch_is_authorized_at_run_time(app, client, tenant_a, database_url, owner_pool, fake_embeddings):
    from tests.e2e.test_ingest_jobs import FILES, stop_workers

    settings = get_settings()
    alias = str(settings.embed_model)
    publish(database_url, tenant_a, {"allowed_kbs": ["legal"], "allowed_models": [alias], "allowed_tools": "*"})
    await stop_workers(app)
    before = len(fake_embeddings.calls)
    accepted = await client.post(
        "/v1/ingest", params={"namespace": "legal"},
        files=FILES(_three_batch_document(), "three-batches.txt"),
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    completed = await _run_queued_ingest(app, job_id)
    decisions = await owner_pool.fetch(
        "SELECT request_id, outcome FROM gateway_decisions WHERE action = 'model.invoke' AND request_id = $1 ORDER BY created_at, id",
        job_id,
    )
    assert completed["status"] == "succeeded"
    assert len(decisions) == 3 and {row["outcome"] for row in decisions} == {"allow"}
    assert {row["request_id"] for row in decisions} == {job_id}
    assert len(fake_embeddings.calls) - before == 3

    # Hold the next job, then publish a policy that excludes its embedding model before the worker starts.
    await stop_workers(app)
    before = len(fake_embeddings.calls)
    denied = await client.post(
        "/v1/ingest", params={"namespace": "legal"},
        files=FILES(_three_batch_document(), "denied-batches.txt"),
    )
    assert denied.status_code == 202, denied.text
    denied_id = denied.json()["job_id"]
    publish(database_url, tenant_a, {"allowed_kbs": ["legal"], "allowed_models": [], "allowed_tools": "*"})
    failed = await _run_queued_ingest(app, denied_id)
    denied_row = await owner_pool.fetchrow(
        "SELECT request_id, outcome, reason FROM gateway_decisions WHERE action = 'model.invoke' AND request_id = $1",
        denied_id,
    )
    assert failed["status"] == "failed" and failed["error_code"] == "model_not_allowed"
    assert denied_row is not None and denied_row["outcome"] == "deny" and denied_row["reason"] == "model_not_allowed"
    assert len(fake_embeddings.calls) == before
    assert await owner_pool.fetchval(
        "SELECT count(*) FROM documents WHERE tenant_id = $1 AND document_id = $2",
        UUID(tenant_a.id), "denied-batches.txt",
    ) == 0

"""Sprint 007 A4 and the jobs API: ingest answers 202 and a worker does the work. The raw bytes are stored once by
SHA-256, the same Idempotency-Key gives the same job, and the job routes are typed, gated and tenant-scoped."""
import asyncio
import hashlib
import json
from uuid import uuid4

from adapters.pg_outbox_events import OutboxRelay
from ports import INGEST_COMPLETED
from tests.e2e.test_gateway_e2e import publish
from tests.e2e.test_search_flow import GDPR, GDPR_V2, QUERY
from tests.fakes import FakeEventBus
from tests.jobs_helpers import wait_for_job

FILES = lambda content=GDPR, name="gdpr.md": {"file": (name, content, "text/markdown")}  # noqa: E731


def stored(tmp_path):
    return sorted(p for p in tmp_path.rglob("*") if p.is_file() and not p.name.startswith(".tmp"))


async def stop_workers(app):
    await app.state.embedded.stop()


async def test_ingest_returns_202_with_a_job_at_once_and_the_job_runs_to_the_end(app, client, tenant_a, fake_llm, fake_embeddings):
    await stop_workers(app)  # nobody runs the job yet: we can look at it queued
    resp = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())
    assert resp.status_code == 202
    body = resp.json()
    assert set(body) == {"job_id", "status"} and body["status"] == "queued"
    job = (await client.get(f"/v1/jobs/{body['job_id']}")).json()
    assert job["kind"] == "ingest" and job["status"] == "queued" and job["attempts"] == 0
    assert job["progress"] == {"done": 0, "total": 0} and job["error_code"] is None
    assert job["resource"] == "legal/gdpr.md" and job["execution_id"] is None and job["max_attempts"] == 5
    assert (await client.get("/v1/documents", params={"namespace": "legal"})).json()["count"] == 0  # nothing ingested yet

    from core.settings import get_settings
    from workers.embedded import start_embedded

    embedded = start_embedded(get_settings(), app.state.db_pool, app.state.adapters, app.state.gateway_runtime,
                              app.state.agent_graph, workers=1, relay=False)
    try:
        await wait_for_job(body["job_id"])
    finally:
        await embedded.stop()
    job = (await client.get(f"/v1/jobs/{body['job_id']}")).json()
    assert job["status"] == "succeeded" and job["attempts"] == 1
    assert job["progress"]["done"] == job["progress"]["total"] > 0
    docs = (await client.get("/v1/documents", params={"namespace": "legal"})).json()
    assert docs["count"] == 1 and docs["documents"][0]["chunk_count"] == job["progress"]["total"]
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200


async def test_the_raw_bytes_are_stored_once_by_sha256_and_a_second_ingest_adds_no_object(client, tmp_path, fake_llm, fake_embeddings):
    digest = hashlib.sha256(GDPR).hexdigest()
    first = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())
    await wait_for_job(first.json()["job_id"])
    [obj] = stored(tmp_path)
    assert obj.name == digest and obj.parent.name == digest[:2] and obj.read_bytes() == GDPR  # keyed by content, stored before parsing
    mtime = obj.stat().st_mtime_ns

    again = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())  # the same file
    other_name = await client.post("/v1/ingest", params={"namespace": "legal", "document_id": "copy.md"}, files=FILES(name="copy.md"))
    for r in (again, other_name):
        assert r.status_code == 202
        await wait_for_job(r.json()["job_id"])
    assert stored(tmp_path) == [obj] and obj.stat().st_mtime_ns == mtime  # no new object, the old one untouched
    await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(GDPR_V2))
    assert len(stored(tmp_path)) == 2  # different bytes are a different object


async def test_the_same_bytes_are_stored_before_the_file_is_parsed(app, client, tmp_path, pool, fake_llm, fake_embeddings, monkeypatch):
    import workers.handlers.ingest as handler_module

    async def refuse(**kwargs):
        raise ValueError("unreadable")

    monkeypatch.setattr(handler_module, "ingestion_pipeline", refuse)
    resp = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(b"\xff\xfe not text"))
    job = await wait_for_job(resp.json()["job_id"])
    assert (job["status"], job["error_code"]) == ("failed", "unsupported_file")
    assert [p.name for p in stored(tmp_path)] == [hashlib.sha256(b"\xff\xfe not text").hexdigest()]  # kept for inspection


async def test_re_ingesting_an_unchanged_file_changes_nothing_and_an_updated_one_replaces_the_chunks(client, pool, fake_llm, fake_embeddings):
    first = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())
    await wait_for_job(first.json()["job_id"])
    chunks = await pool.fetchval("SELECT count(*) FROM documents")
    again = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())
    row = await wait_for_job(again.json()["job_id"])
    assert row["status"] == "succeeded" and json.loads(row["result"])["status"] == "unchanged"
    assert await pool.fetchval("SELECT count(*) FROM documents") == chunks
    new = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(GDPR_V2))
    row = await wait_for_job(new.json()["job_id"])
    assert json.loads(row["result"])["status"] == "updated"
    assert await pool.fetchval("SELECT count(*) FROM documents WHERE content LIKE '%48 hours%'") == chunks
    assert await pool.fetchval("SELECT count(*) FROM documents WHERE content LIKE '%72 hours%'") == 0


async def test_an_idempotency_key_returns_the_same_job_with_200(client, client_b, pool, tmp_path, fake_llm, fake_embeddings):
    headers = {"Idempotency-Key": "upload-42"}
    first = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(), headers=headers)
    second = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(GDPR_V2), headers=headers)
    assert (first.status_code, second.status_code) == (202, 200)
    assert second.json()["job_id"] == first.json()["job_id"]
    await wait_for_job(first.json()["job_id"])
    assert await pool.fetchval("SELECT count(*) FROM jobs") == 1
    assert len(stored(tmp_path)) == 1  # the repeat did not even store its file
    theirs = await client_b.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(), headers=headers)
    assert theirs.status_code == 202 and theirs.json()["job_id"] != first.json()["job_id"]  # per tenant
    bad = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(), headers={"Idempotency-Key": "has space"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_idempotency_key"


async def test_ingest_is_still_gated_before_a_job_exists(client, make_client, tenant_a, pool, fake_llm, fake_embeddings):
    missing = await client.post("/v1/ingest", params={"namespace": "no-such-kb"}, files=FILES())
    assert missing.status_code == 404
    reader = make_client(tenant_a.headers("reader"))
    assert (await reader.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())).status_code == 403
    assert await pool.fetchval("SELECT count(*) FROM jobs") == 0
    assert (await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(), headers={})).status_code == 202


async def test_a_long_document_id_is_refused_not_stored_in_the_payload(client, pool, fake_llm, fake_embeddings):
    resp = await client.post("/v1/ingest", params={"namespace": "legal", "document_id": "x" * 5000}, files=FILES())
    assert resp.status_code == 413 and await pool.fetchval("SELECT count(*) FROM jobs") == 0


# ------------------------------------------------------------------ the jobs routes

async def test_jobs_are_tenant_scoped_a_foreign_and_a_missing_job_give_the_same_404(client, client_b, fake_llm, fake_embeddings):
    mine = (await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())).json()["job_id"]
    foreign = await client_b.get(f"/v1/jobs/{mine}")
    missing = await client_b.get(f"/v1/jobs/{uuid4()}")
    assert foreign.status_code == missing.status_code == 404
    strip = lambda r: {k: v for k, v in r.json()["error"].items() if k != "request_id"}  # noqa: E731
    assert strip(foreign) == strip(missing)
    assert (await client_b.get("/v1/jobs")).json() == {"items": [], "next_cursor": None}
    assert [j["id"] for j in (await client.get("/v1/jobs")).json()["items"]] == [mine]


async def test_the_job_routes_need_kb_read_and_leave_a_decision_row(make_client, tenant_a, pool, client, fake_llm, fake_embeddings):
    no_read = make_client(tenant_a.headers("query_only"))
    assert (await no_read.get("/v1/jobs")).status_code == 403
    assert (await no_read.get(f"/v1/jobs/{uuid4()}")).status_code == 403
    before = await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE action = 'kb.read' AND outcome = 'allow'")
    assert (await client.get("/v1/jobs")).status_code == 200
    await client.get(f"/v1/jobs/{uuid4()}")
    after = await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE action = 'kb.read' AND outcome = 'allow'")
    assert after == before + 2  # every read goes through enforce()


async def test_the_list_filters_by_kind_and_status_and_pages_with_a_cursor(app, client, fake_llm, fake_embeddings):
    await stop_workers(app)
    ids = [(await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES(GDPR + bytes([i]), f"d{i}.md"))).json()["job_id"] for i in range(5)]
    page1 = (await client.get("/v1/jobs", params={"limit": 2})).json()
    page2 = (await client.get("/v1/jobs", params={"limit": 2, "cursor": page1["next_cursor"]})).json()
    page3 = (await client.get("/v1/jobs", params={"limit": 2, "cursor": page2["next_cursor"]})).json()
    got = [j["id"] for p in (page1, page2, page3) for j in p["items"]]
    assert got == list(reversed(ids)) and page3["next_cursor"] is None  # newest first, no repeats, no gaps
    assert len((await client.get("/v1/jobs", params={"kind": "ingest", "status": "queued"})).json()["items"]) == 5
    assert (await client.get("/v1/jobs", params={"kind": "agent_run"})).json()["items"] == []
    assert (await client.get("/v1/jobs", params={"status": "running"})).json()["items"] == []
    assert (await client.get("/v1/jobs", params={"status": "bogus"})).status_code == 422
    assert (await client.get("/v1/jobs", params={"cursor": "nonsense"})).status_code == 400
    assert (await client.get("/v1/jobs/not-a-uuid")).status_code == 422


async def test_a_policy_that_hides_a_knowledge_base_hides_its_jobs(client, database_url, tenant_a, fake_llm, fake_embeddings):
    legal = (await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())).json()["job_id"]
    default = (await client.post("/v1/ingest", params={"namespace": "default"}, files=FILES(GDPR_V2, "x.md"))).json()["job_id"]
    publish(database_url, tenant_a, {"allowed_kbs": ["default"], "allowed_models": "*", "allowed_tools": "*"})
    assert [j["id"] for j in (await client.get("/v1/jobs")).json()["items"]] == [default]
    assert (await client.get(f"/v1/jobs/{legal}")).status_code == 404
    assert (await client.get(f"/v1/jobs/{default}")).status_code == 200


# ------------------------------------------------------------------ the outbox

async def test_a_finished_ingest_writes_its_event_to_the_outbox_in_the_same_transaction(app, client, tenant_a, pool, fake_llm, fake_embeddings):
    resp = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())
    job = await wait_for_job(resp.json()["job_id"])
    [event] = [json.loads(r["event"]) for r in await pool.fetch("SELECT event FROM outbox") if json.loads(r["event"])["type"] == INGEST_COMPLETED]
    assert event["data"] == {
        "job_id": resp.json()["job_id"], "document_id": "gdpr.md", "namespace": "legal",
        "content_hash": json.loads(job["payload"])["content_hash"], "status": "new", "total_chunks": job["progress_total"],
    }
    assert event["tenantid"] == tenant_a.id and "72 hours" not in json.dumps(event)  # no document text
    target = FakeEventBus()
    await OutboxRelay(app.state.db_pool, target).run_once()
    assert INGEST_COMPLETED in {e.type for e in target.published}


async def test_a_job_whose_event_cannot_be_written_does_not_succeed_and_is_tried_again(app, client, pool, fake_llm, fake_embeddings, monkeypatch):
    real = app.state.adapters.events.publish
    calls = []

    async def flaky(event, *, tx=None):
        if event.type == INGEST_COMPLETED:
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError("outbox write failed")
        await real(event, tx=tx)

    monkeypatch.setattr(app.state.adapters.events, "publish", flaky)
    resp = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())
    row = await wait_for_job(resp.json()["job_id"])
    assert row["status"] == "succeeded" and row["attempts"] == 2  # the first attempt's success rolled back with its event
    assert await pool.fetchval("SELECT count(*) FROM outbox WHERE event->>'type' = $1", INGEST_COMPLETED) == 1


async def test_every_decision_leaves_one_outbox_event_in_its_own_transaction(client, pool, fake_llm, fake_embeddings):
    resp = await client.post("/v1/ingest", params={"namespace": "legal"}, files=FILES())
    await wait_for_job(resp.json()["job_id"])
    await client.post("/v1/search", json=QUERY)
    decisions = {str(r["id"]) for r in await pool.fetch("SELECT id FROM gateway_decisions")}
    events = {json.loads(r["event"])["data"]["decision_id"] for r in await pool.fetch(
        "SELECT event FROM outbox WHERE event->>'type' = 'platform.gateway.decision.v1'")}
    assert decisions and events == decisions


async def test_the_embedded_relay_marks_events_sent(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    from core.settings import get_settings
    from workers.embedded import start_embedded

    await client.get("/v1/jobs")
    assert await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL") > 0
    relay = start_embedded(get_settings(), app.state.db_pool, app.state.adapters, app.state.gateway_runtime,
                           app.state.agent_graph, workers=0, relay=True)
    try:
        for _ in range(100):
            if await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL") == 0:
                break
            await asyncio.sleep(0.1)
    finally:
        await relay.stop()
    assert await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL") == 0

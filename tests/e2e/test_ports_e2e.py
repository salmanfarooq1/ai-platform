"""Sprint 006 end to end, through the real app built by the registry: embedding provenance and stale vectors, the
embedding fallback, one CloudEvent per recorded decision, and agent runs through the AgentRuntime."""
import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from asgi_lifespan import LifespanManager

from adapters.litellm_embeddings import LitellmEmbeddings
from api.main import create_app
from core.identity.admin import admin_connection
from core.settings import get_settings
from gateway.admin import set_policy
from ports import DECISION_RECORDED, RunState
from tests.e2e.conftest import adapter_overrides, eventually
from tests.e2e.test_search_flow import QUERY, ingest
from tests.fakes import FakeEmbeddings, FakeLLM, fake_embedding

AGENT = {"question": "breach notification supervisory authority 72 hours", "namespace": "legal"}
OTHER_MODEL = "test/other-embedding-model"


async def second_app(request, tenant, **extra):
    """A second app on the same database and Redis, as after a restart with another EMBED_MODEL."""
    overrides = {**adapter_overrides(request), **extra}
    application = create_app(adapter_overrides=overrides)
    manager = LifespanManager(application)
    await manager.__aenter__()
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    client = httpx.AsyncClient(transport=transport, base_url="http://test", headers=tenant.headers("full"))
    return application, client, manager


# ------------------------------------------------------------------ embedding provenance and stale vectors

async def test_ingested_chunks_record_the_model_and_dimension_that_produced_them(client, pool, fake_llm, fake_embeddings):
    await ingest(client)
    rows = await pool.fetch("SELECT DISTINCT embedding_model, embedding_dim FROM documents")
    assert [(r["embedding_model"], r["embedding_dim"]) for r in rows] == [(get_settings().embed_model, 768)]
    assert await pool.fetchval("SELECT count(*) FROM documents WHERE embedding_model IS NULL OR embedding_dim IS NULL") == 0


async def test_health_reports_no_stale_vectors_for_a_fresh_corpus(client, anon_client, fake_llm, fake_embeddings):
    await ingest(client)
    body = (await anon_client.get("/v1/health")).json()
    assert body["stale_vectors"] == 0 and body["embedding"] == "ok"


async def test_changing_the_embedding_model_makes_old_chunks_stale_not_wrong(
    request, client, anon_client, pool, tenant_a, fake_llm, fake_embeddings,
):
    chunks = (await ingest(client)).json()["total_chunks"]
    first = await client.post("/v1/search", json=QUERY)
    assert first.status_code == 200 and "72 hours" in first.json()["answer"]  # works with the model it was embedded with

    # "Restart" with another embedding model: same database, same Redis (so the exact cache is still full).
    other = FakeEmbeddings(model=OTHER_MODEL)
    application, client2, manager = await second_app(request, tenant_a, embeddings=other)
    try:
        health = (await client2.get("/v1/health")).json()
        assert health["stale_vectors"] == chunks > 0

        for mode in ("hybrid", "vector_only", "bm25_only"):  # no search finds an old chunk, text search included
            resp = await client2.post("/v1/search", json={**QUERY, "retrieval_mode": mode})
            assert resp.status_code == 404, (mode, resp.text)
            assert "No documents found" in resp.json()["error"]["message"]
        assert fake_llm.kinds == ["synthesis"]  # only the first search ever reached the LLM
        # the first answer is not served from the cache either: the key carries the model
        assert (await client2.post("/v1/search", json=QUERY)).status_code == 404
        # the old rows are still there, untouched: stale, not deleted
        assert await pool.fetchval("SELECT count(*) FROM documents") == chunks

        # re-ingesting under the new model (the document is unchanged, so replace it) makes it searchable again
        await client2.post("/v1/ingest", params={"namespace": "legal"}, files={"file": (
            "gdpr2.md", b"# GDPR\n\nBreach notification supervisory authority within 72 hours.\n", "text/markdown")})
        found = await client2.post("/v1/search", json=QUERY)
        assert found.status_code == 200 and found.json()["results"][0]["document_id"] == "gdpr2.md"
        assert (await client2.get("/v1/health")).json()["stale_vectors"] == chunks  # the old ones are still stale
    finally:
        await client2.aclose()
        await manager.__aexit__(None, None, None)


async def test_the_semantic_cache_is_not_shared_across_embedding_models(
    request, client, tenant_a, fake_llm, fake_embeddings,
):
    await ingest(client)
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200
    near = {**QUERY, "query": QUERY["query"] + " please"}
    assert (await client.post("/v1/search", json=near)).headers["X-Cache-Type"] == "semantic"  # same model: a hit

    application, client2, manager = await second_app(request, tenant_a, embeddings=FakeEmbeddings(model=OTHER_MODEL))
    try:
        resp = await client2.post("/v1/search", json=near)
        assert resp.status_code == 404 and resp.headers.get("X-Cache") != "HIT"
    finally:
        await client2.aclose()
        await manager.__aexit__(None, None, None)


# ------------------------------------------------------------------ the embedding fallback

class Providers:
    """Scripted embedding providers: `down` raise, the others answer with vectors of their own width."""

    def __init__(self, widths: dict[str, int], down: set[str] = frozenset()):
        self.widths, self.down, self.calls = widths, set(down), []

    async def __call__(self, *, model, input, **kwargs):
        self.calls.append(model)
        if model in self.down:
            raise ConnectionError(f"{model} is down")
        width = self.widths[model]
        return SimpleNamespace(data=[{"embedding": (fake_embedding(t) * 8)[:width]} for t in input])


async def test_the_fallback_embeds_when_the_primary_fails_and_the_rows_say_which_model_did(
    request, tenant_a, pool, fake_llm,
):
    providers = Providers({"primary/embed": 768, "fallback/embed": 768}, down={"primary/embed"})
    embeddings = LitellmEmbeddings("primary/embed", 768, ["fallback/embed"], call=providers)
    application, client, manager = await second_app(request, tenant_a, embeddings=embeddings)
    try:
        resp = await ingest(client)
        assert resp.status_code == 200
        rows = await pool.fetch("SELECT DISTINCT embedding_model, embedding_dim FROM documents")
        assert [(r["embedding_model"], r["embedding_dim"]) for r in rows] == [("fallback/embed", 768)]
        assert providers.calls[:2] == ["primary/embed", "fallback/embed"]  # the primary was tried first
        # the query is embedded by the fallback too, so it compares like with like and finds the chunk
        found = await client.post("/v1/search", json=QUERY)
        assert found.status_code == 200 and "72 hours" in found.json()["answer"]
        # the primary is the active model, so these fallback-made vectors are reported as not current
        assert (await client.get("/v1/health")).json()["stale_vectors"] >= 1
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


async def test_a_fallback_with_another_dimension_is_refused_and_logged(request, tenant_a, pool, fake_llm, json_logs):
    providers = Providers({"primary/embed": 768, "fallback/narrow": 512}, down={"primary/embed"})
    embeddings = LitellmEmbeddings("primary/embed", 768, ["fallback/narrow"], call=providers)
    application, client, manager = await second_app(request, tenant_a, embeddings=embeddings)
    try:
        failed = await ingest(client)
        assert failed.status_code == 500 and failed.json()["error"]["message"] == "Ingestion failed"
        assert await pool.fetchval("SELECT count(*) FROM documents") == 0  # nothing stored with the wrong width
        searched = await client.post("/v1/search", json=QUERY)
        assert searched.status_code == 502 and "Embedding provider failed" in searched.json()["error"]["message"]
        assert "512" in searched.json()["error"]["message"] or "768" in searched.json()["error"]["message"]
        refused = [line for line in json_logs() if "embedding provider refused" in line.get("message", "")]
        assert refused and "fallback/narrow" in refused[0]["message"] and refused[0]["level"] == "ERROR"
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


# ------------------------------------------------------------------ one CloudEvent per recorded decision

async def test_every_recorded_decision_publishes_one_event_with_no_input_text(
    app, client, pool, tenant_a, database_url, fake_llm, fake_embeddings,
):
    seen = []

    async def record(event, tx):
        # `tx` is the connection that wrote the decision: its (uncommitted) row is visible only through it.
        row_visible_in_tx = await tx.fetchval("SELECT count(*) FROM gateway_decisions WHERE id = $1", UUID(event.subject))
        seen.append((event, row_visible_in_tx))

    app.state.adapters.events.subscribe(DECISION_RECORDED, record)
    await ingest(client)
    secret_query = {**QUERY, "query": "what does the hush-hush project zephyr require about breach notification"}
    assert (await client.post("/v1/search", json=secret_query)).status_code == 200
    with admin_connection(database_url) as conn:
        set_policy(conn, tenant_a.slug, {"allowed_kbs": ["legal"], "allowed_models": "*", "allowed_tools": "*"}, "tests")
    denied = await client.post("/v1/search", json={**QUERY, "namespace": "kyc_aml"})
    assert denied.status_code == 403
    assert (await client.post("/v1/agent/query", json={**AGENT, "enable_verifier": False})).status_code == 200

    rows = await pool.fetch("SELECT * FROM gateway_decisions WHERE tenant_id = $1 ORDER BY created_at, id", UUID(tenant_a.id))
    assert rows and len(seen) == len(rows)  # exactly one event per recorded decision
    by_id = {str(r["id"]): r for r in rows}
    assert set(by_id) == {event.subject for event, _ in seen}
    for event, row_visible_in_tx in seen:
        row = by_id[event.subject]
        assert row_visible_in_tx == 1  # the handler ran inside the transaction that wrote the row
        assert event.type == "platform.gateway.decision.v1" and event.specversion == "1.0"
        assert event.source == "/gateway" and event.tenantid == tenant_a.id
        assert event.data == {
            "decision_id": str(row["id"]), "outcome": row["outcome"], "stage": row["stage"], "reason": row["reason"],
            "action": row["action"], "resource": row["resource"], "request_id": row["request_id"],
            "execution_id": str(row["execution_id"]) if row["execution_id"] else None,
        }
    everything = json.dumps([event.to_dict() for event, _ in seen])
    assert "zephyr" not in everything and "hush-hush" not in everything and "breach notification" not in everything
    assert {e.data["reason"] for e, _ in seen if e.data["outcome"] == "deny"} == {"kb_not_allowed"}  # denies publish too
    assert any(e.data["outcome"] == "allow" and e.data["action"] == "agent.run" for e, _ in seen)


async def test_a_failing_event_bus_fails_the_decision_closed(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    """A bug in a subscriber that raises out of the bus (an outbox that cannot write) must not let an action
    through unrecorded: the allow becomes a 503 `decision_unrecorded` and the row is rolled back."""
    class Boom:
        def subscribe(self, type, handler):
            pass

        async def publish(self, event, *, tx=None):
            raise RuntimeError("outbox write failed")

    await ingest(client)
    before = await pool.fetchval("SELECT count(*) FROM gateway_decisions")
    real = app.state.gateway_runtime.events
    app.state.gateway_runtime.events = Boom()
    try:
        resp = await client.post("/v1/search", json=QUERY)
    finally:
        app.state.gateway_runtime.events = real
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "decision_unrecorded"
    assert await pool.fetchval("SELECT count(*) FROM gateway_decisions") == before  # nothing half-recorded
    assert fake_llm.calls == []  # and no model was called


async def test_a_subscriber_that_raises_does_not_break_the_request(app, client, pool, fake_llm, fake_embeddings):
    async def broken(event, tx):
        raise RuntimeError("subscriber bug")

    app.state.adapters.events.subscribe(DECISION_RECORDED, broken)
    assert (await ingest(client)).status_code == 200
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200
    assert await pool.fetchval("SELECT count(*) FROM gateway_decisions") > 0


# ------------------------------------------------------------------ agent runs go through the AgentRuntime

async def test_an_agent_query_runs_through_the_runtime_and_stamps_its_execution_id_on_every_decision(
    app, client, pool, tenant_a, fake_llm, fake_embeddings,
):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200  # a decision with no run
    resp = await client.post("/v1/agent/query", json={**AGENT, "enable_verifier": True})
    assert resp.status_code == 200 and resp.json()["tool_calls_made"] == 1

    run_rows = await pool.fetch(
        "SELECT * FROM gateway_decisions WHERE tenant_id = $1 AND execution_id IS NOT NULL ORDER BY created_at, id", UUID(tenant_a.id))
    ids = {r["execution_id"] for r in run_rows}
    assert len(ids) == 1  # one run, one execution id
    [execution_id] = ids
    assert {r["action"] for r in run_rows} >= {"agent.run", "model.invoke", "tool.call", "kb.read"}
    run_request = {r["request_id"] for r in run_rows}
    assert len(run_request) == 1  # every decision of the agent request carries it ...
    same_request = await pool.fetch("SELECT execution_id FROM gateway_decisions WHERE request_id = $1", run_request.pop())
    assert {r["execution_id"] for r in same_request} == {execution_id}  # ... and none of the request lacks it
    others = await pool.fetch(
        "SELECT action, execution_id FROM gateway_decisions WHERE tenant_id = $1 AND execution_id IS NULL", UUID(tenant_a.id))
    assert {r["action"] for r in others} >= {"kb.write", "kb.read", "model.invoke"}  # ingest and search belong to no run

    status = await app.state.adapters.runtime.status(str(execution_id))
    assert status.state is RunState.SUCCEEDED and status.tenant_id == UUID(tenant_a.id) and status.kind == "agent.query"


async def test_a_denied_agent_entry_still_records_the_execution_id_it_would_have_had(app, client, pool, tenant_a, fake_llm):
    resp = await client.post("/v1/agent/query", json={**AGENT, "namespace": "no-such-kb"})
    assert resp.status_code == 404
    rows = await pool.fetch("SELECT execution_id, action FROM gateway_decisions WHERE tenant_id = $1", UUID(tenant_a.id))
    assert rows and len({r["execution_id"] for r in rows}) == 1 and rows[0]["execution_id"] is not None
    with pytest.raises(KeyError):
        await app.state.adapters.runtime.status(str(rows[0]["execution_id"]))  # no run was ever started


async def test_a_run_that_crashes_is_a_500_with_the_standard_error_and_a_failed_status(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    class Crashing(FakeLLM):
        async def acompletion(self, **kwargs):
            raise RuntimeError("model exploded")

    fake_llm.use(Crashing())
    resp = await client.post("/v1/agent/query", json=AGENT)
    assert resp.status_code == 500
    assert resp.json()["error"]["message"] == "Agent execution failed: model exploded"
    [execution_id] = {r["execution_id"] for r in await pool.fetch(
        "SELECT execution_id FROM gateway_decisions WHERE execution_id IS NOT NULL")}
    status = await app.state.adapters.runtime.status(str(execution_id))
    assert status.state is RunState.FAILED and status.error == "model exploded"


async def test_a_client_that_disconnects_mid_run_stops_the_run(app, client, tenant_a, fake_llm, fake_embeddings):
    """Cancelling the request cancels the run, including the model call it is inside (cleanup stops it)."""
    started, cancelled = asyncio.Event(), asyncio.Event()

    class Slow(FakeLLM):
        async def acompletion(self, **kwargs):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    fake_llm.use(Slow())
    task = asyncio.create_task(client.post("/v1/agent/query", json=AGENT))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(cancelled.wait(), 5)  # the model call inside the run was cancelled, not left running
    runtime = app.state.adapters.runtime
    await eventually(lambda: all(e.status.state.terminal for e in runtime._runs.values()))
    assert [e.status.state for e in runtime._runs.values()] == [RunState.STOPPED]


async def test_stopping_a_real_agent_run_during_a_tool_call_cancels_the_tool(app, tenant_a, fake_llm, fake_embeddings):
    """The same stop the contract tests, on the real LangGraph agent: the run is inside `retrieve_chunks` (it is
    embedding the query) when it is stopped."""
    from api.agent.runner import AGENT_RUN_KIND
    from gateway import build_context
    from ports import RunSpec
    from tests.db_fixtures import principal_of

    fake_llm.agent_namespace = "legal"
    in_tool, tool_cancelled = asyncio.Event(), asyncio.Event()

    async def slow_embed(texts):
        in_tool.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            tool_cancelled.set()
            raise

    fake_embeddings.embed = slow_embed  # the retrieve tool embeds the query: that is where the run is stuck
    ctx = await build_context(app.state.gateway_runtime, principal_of(tenant_a), "req-stop", "t" * 32)
    runtime = app.state.adapters.runtime
    handle = await runtime.start(RunSpec(
        kind=AGENT_RUN_KIND, tenant_id=UUID(tenant_a.id), context=ctx,
        input={**AGENT, "max_iterations": 3, "enable_verifier": False, "max_verify_retries": 0},
    ))
    await asyncio.wait_for(in_tool.wait(), 5)
    assert (await runtime.status(handle.run_id)).state is RunState.RUNNING

    stopped = await runtime.stop(handle.run_id)

    assert stopped.state is RunState.STOPPED
    assert tool_cancelled.is_set()  # the tool call was cancelled mid-flight
    assert ctx.execution_id == handle.execution_id  # the run stamped its id on the context its decisions use
    await runtime.cleanup(handle.run_id)


async def test_the_console_shows_a_runs_execution_id_and_runtime_status_to_its_own_tenant_only(
    app, client, make_client, pool, tenant_a, tenant_b, database_url, fake_llm, fake_embeddings,
):
    from tests.e2e.web_helpers import bearer, key_with

    fake_llm.agent_namespace = "legal"
    await ingest(client)
    assert (await client.post("/v1/agent/query", json={**AGENT, "enable_verifier": False})).status_code == 200
    audit_a = make_client(bearer(key_with(database_url, tenant_a, ["audit:read"])[0]))
    audit_b = make_client(bearer(key_with(database_url, tenant_b, ["audit:read"])[0]))

    [run] = (await audit_a.get("/v1/decisions", params={"action": "agent.run"})).json()["items"]
    assert run["execution_id"] and run["run_status"] == "succeeded"
    detail = (await audit_a.get(f"/v1/decisions/{run['id']}")).json()
    assert detail["execution_id"] == run["execution_id"] and detail["run_status"] == "succeeded"
    assert {t["execution_id"] for t in detail["trace"]} == {run["execution_id"]}  # the whole request is one run
    assert [t["run_status"] for t in detail["trace"] if t["action"] == "agent.run"] == ["succeeded"]
    assert all(t["run_status"] is None for t in detail["trace"] if t["action"] != "agent.run")  # only the run's own row
    by_request = (await audit_a.get(f"/v1/requests/{run['request_id']}")).json()
    assert [d["run_status"] for d in by_request["decisions"] if d["action"] == "agent.run"] == ["succeeded"]

    # Another tenant's decision that names this execution id (it cannot happen through the API) gets no status:
    # the runtime knows the run belongs to tenant A.
    await pool.execute(
        "INSERT INTO gateway_decisions (tenant_id, request_id, trace_id, action, outcome, stage, reason, execution_id) "
        "VALUES ($1, 'req-b', 'tb', 'agent.run', 'allow', 'allow', 'allowed', $2)", UUID(tenant_b.id), UUID(run["execution_id"]))
    [theirs] = (await audit_b.get("/v1/decisions", params={"action": "agent.run"})).json()["items"]
    assert theirs["execution_id"] == run["execution_id"] and theirs["run_status"] is None

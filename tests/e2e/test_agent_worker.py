"""Sprint 007 A5: an agent run executes in a worker, through the AgentRuntime, and its decisions carry the
execution id. `/v1/agent/query` waits up to the sync wait and then answers 202; `/v1/agent/runs` is durable."""
import asyncio
import json
from uuid import UUID, uuid4

import pytest

from adapters.job_runtime import JobAgentRuntime
from core.settings import get_settings
from ports import RunState
from tests.e2e.test_gateway_e2e import publish
from tests.e2e.test_search_flow import ingest
from tests.e2e.web_helpers import bearer, key_with
from tests.fakes import FakeLLM
from workers.embedded import start_embedded

AGENT = {"question": "breach notification supervisory authority 72 hours", "namespace": "legal"}


@pytest.fixture
def short_wait(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_sync_wait_seconds", 0.4)


def start_worker(app):
    return start_embedded(get_settings(), app.state.db_pool, app.state.adapters, app.state.gateway_runtime,
                          app.state.agent_graph, workers=1, relay=False)


async def until(check, timeout=15.0):
    end = asyncio.get_running_loop().time() + timeout
    while True:
        value = await check()
        if value:
            return value
        assert asyncio.get_running_loop().time() < end, "not in time"
        await asyncio.sleep(0.05)


async def test_the_run_executes_in_the_worker_not_in_the_request(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    seen = {}
    real = app.state.agent_graph.ainvoke

    async def spy(state, config):
        seen["task"] = asyncio.current_task().get_name() if asyncio.current_task() else None
        seen["worker_job"] = await pool.fetchval("SELECT locked_by FROM jobs WHERE kind = 'agent_run'")  # held by a worker slot
        return await real(state, config)

    app.state.agent_graph.ainvoke = spy
    resp = await client.post("/v1/agent/query", json=AGENT)
    assert resp.status_code == 200 and resp.json()["tool_calls_made"] == 1
    assert seen["worker_job"].startswith("embedded/")
    [job] = await pool.fetch("SELECT * FROM jobs WHERE kind = 'agent_run'")
    assert job["status"] == "succeeded" and job["attempts"] == 1 and job["started_at"] and job["resource"] == "legal"
    assert job["payload"] is not None and "input" not in json.loads(job["payload"])  # the question is dropped once the job ends
    assert json.loads(job["result"])["response"]["answer"] == resp.json()["answer"]


async def test_every_decision_of_the_run_carries_the_execution_id_the_job_has(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    await client.post("/v1/search", json={"query": "x", "namespace": "legal"})
    assert (await client.post("/v1/agent/query", json=AGENT)).status_code == 200
    [job] = await pool.fetch("SELECT execution_id FROM jobs WHERE kind = 'agent_run'")
    run_rows = await pool.fetch("SELECT action, execution_id FROM gateway_decisions WHERE execution_id IS NOT NULL")
    assert {r["execution_id"] for r in run_rows} == {job["execution_id"]}
    assert {r["action"] for r in run_rows} >= {"agent.run", "model.invoke", "tool.call", "kb.read"}
    # the calls the worker made (model, tool, KB) are in the same request as the entry decision
    [request_id] = {r["request_id"] for r in await pool.fetch("SELECT request_id FROM gateway_decisions WHERE execution_id IS NOT NULL")}
    assert await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE request_id = $1 AND execution_id IS NULL", request_id) == 0


async def test_usage_is_booked_once_by_the_worker_and_the_headers_still_show_the_cost(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    resp = await client.post("/v1/agent/query", json=AGENT)
    assert resp.status_code == 200 and "X-Cost-USD" in resp.headers and "X-Query-ID" in resp.headers
    assert int(resp.headers["X-Tokens-In"]) > 0
    await asyncio.sleep(0.2)
    assert await pool.fetchval("SELECT count(*) FROM usage_log WHERE endpoint = '/v1/agent/query'") == 1  # not booked twice
    assert "X-Budget-Remaining" in resp.headers


async def test_a_slow_run_answers_202_and_is_read_from_the_runs_endpoint_until_it_finishes(
    app, client, make_client, pool, tenant_a, database_url, fake_llm, fake_embeddings, short_wait,
):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    await app.state.embedded.stop()  # no worker: the run waits in the queue
    resp = await client.post("/v1/agent/query", json=AGENT)
    assert resp.status_code == 202
    accepted = resp.json()
    assert set(accepted) == {"execution_id", "job_id"}
    run = (await client.get(f"/v1/agent/runs/{accepted['execution_id']}")).json()
    assert run["status"] == "queued" and run["result"] is None and run["job_id"] == accepted["job_id"]
    assert run["decisions_url"] == f"/v1/decisions?execution_id={accepted['execution_id']}"

    worker = start_worker(app)
    try:
        async def finished():
            r = (await client.get(f"/v1/agent/runs/{accepted['execution_id']}")).json()
            return r if r["status"] == "succeeded" else None

        done = await until(finished)
    finally:
        await worker.stop()
    assert done["result"]["answer"] and done["result"]["tool_calls_made"] == 1 and done["finished_at"]
    # an audit reader can read it too, and follow the link to the decisions the run caused
    audit = make_client(bearer(key_with(database_url, tenant_a, ["audit:read"])[0]))
    assert (await audit.get(f"/v1/agent/runs/{accepted['execution_id']}")).json()["status"] == "succeeded"
    decisions = (await audit.get(done["decisions_url"])).json()["items"]
    assert decisions and {d["execution_id"] for d in decisions} == {accepted["execution_id"]}
    assert (await pool.fetchval("SELECT count(*) FROM usage_log WHERE endpoint = '/v1/agent/query'")) == 1  # the 202 path books too


async def test_a_run_status_is_durable_it_survives_a_new_runtime_and_a_new_process(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    assert (await client.post("/v1/agent/query", json=AGENT)).status_code == 200
    [row] = await pool.fetch("SELECT execution_id FROM jobs WHERE kind = 'agent_run'")
    fresh = JobAgentRuntime(app.state.db_pool)  # as after a restart: nothing in memory
    status = await fresh.status(str(row["execution_id"]))
    assert status.state is RunState.SUCCEEDED and status.tenant_id == UUID(tenant_a.id) and status.kind == "agent.query"
    result = await fresh.wait(str(row["execution_id"]))
    assert result.output["response"]["answer"]


async def test_the_runs_endpoints_are_scoped_gated_and_tenant_isolated(
    client, client_b, make_client, tenant_a, pool, database_url, fake_llm, fake_embeddings,
):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    assert (await client.post("/v1/agent/query", json=AGENT)).status_code == 200
    listed = (await client.get("/v1/agent/runs")).json()
    [item] = listed["items"]
    assert item["status"] == "succeeded" and listed["next_cursor"] is None
    assert (await client.get(f"/v1/agent/runs/{item['execution_id']}")).status_code == 200
    foreign, missing = await client_b.get(f"/v1/agent/runs/{item['execution_id']}"), await client_b.get(f"/v1/agent/runs/{uuid4()}")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["message"] == missing.json()["error"]["message"]
    assert (await client_b.get("/v1/agent/runs")).json()["items"] == []
    reader = make_client(tenant_a.headers("reader"))  # kb:read only: neither agent nor audit:read
    assert (await reader.get("/v1/agent/runs")).status_code == 403
    assert (await reader.get(f"/v1/agent/runs/{item['execution_id']}")).status_code == 403
    # reading runs is not an agent run: it adds no `agent.run` decision
    assert await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE action = 'agent.run' AND outcome = 'allow'") == 1
    assert (await client.get("/v1/agent/runs", params={"limit": 0})).status_code == 422
    assert (await client.get("/v1/agent/runs", params={"cursor": "bad"})).status_code == 400


async def test_a_run_keeps_the_boundary_of_the_request_that_started_it(
    app, client, pool, tenant_a, database_url, fake_llm, fake_embeddings, short_wait,
):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    await app.state.embedded.stop()
    assert (await client.post("/v1/agent/query", json=AGENT)).status_code == 202
    # A policy published while the run waits does not apply to it (the boundary is fixed at request start).
    publish(database_url, tenant_a, {"allowed_kbs": ["default"], "allowed_models": "*", "allowed_tools": "*"})
    worker = start_worker(app)
    try:
        async def done():
            return await pool.fetchval("SELECT status FROM jobs WHERE kind = 'agent_run'") == "succeeded"

        await until(done)
    finally:
        await worker.stop()
    versions = {r["policy_version"] for r in await pool.fetch(
        "SELECT policy_version FROM gateway_decisions WHERE execution_id IS NOT NULL AND action IN ('tool.call', 'kb.read', 'model.invoke')")}
    assert versions == {None}  # no policy when the request started: the run kept that, not the version published since
    denied = await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE execution_id IS NOT NULL AND outcome = 'deny'")
    assert denied == 0  # `legal` was allowed when the request started, and the run kept that


async def test_a_crashing_run_is_failed_once_with_the_error_not_retried(app, client, pool, tenant_a, fake_llm, fake_embeddings):
    class Crashing(FakeLLM):
        async def acompletion(self, **kwargs):
            raise RuntimeError("model exploded")

    fake_llm.use(Crashing())
    resp = await client.post("/v1/agent/query", json=AGENT)
    assert resp.status_code == 500 and resp.json()["error"]["message"] == "Agent execution failed"
    assert "model exploded" not in resp.text
    [job] = await pool.fetch("SELECT * FROM jobs WHERE kind = 'agent_run'")
    assert (job["status"], job["error_code"], job["attempts"]) == ("failed", "agent_run_failed", 1)
    assert job["error_detail"] is None  # QA L2: the exception text is not stored in the job row
    run = (await client.get(f"/v1/agent/runs/{job['execution_id']}")).json()
    assert run["status"] == "failed" and run["error_code"] == "agent_run_failed" and run["result"] is None
    assert "model exploded" not in json.dumps(run)  # the exception text is not in the run's API
    assert await pool.fetchval("SELECT count(*) FROM usage_log WHERE endpoint = '/v1/agent/query'") == 0


async def test_a_too_long_question_is_refused_at_the_entry(client, pool, fake_llm, fake_embeddings):
    resp = await client.post("/v1/agent/query", json={**AGENT, "question": "q" * 5000})
    assert resp.status_code in (400, 413) and await pool.fetchval("SELECT count(*) FROM jobs") == 0


# ------------------------------------------------------------------ QA fixes M1 and M2

def other_principal_headers(dsn, scopes):
    """A second principal of tenant-a with its own key."""
    from core.identity.admin import admin_connection, create_key, create_principal

    with admin_connection(dsn) as conn:
        pid = create_principal(conn, "tenant-a", "service", f"second-{'-'.join(scopes)}")
        return pid, bearer(create_key(conn, pid, scopes).token)


async def test_m1_a_policy_that_hides_a_knowledge_base_hides_its_runs_and_answers(
    client, pool, tenant_a, database_url, fake_llm, fake_embeddings,
):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    assert (await client.post("/v1/agent/query", json=AGENT)).status_code == 200
    [row] = await pool.fetch("SELECT execution_id FROM jobs WHERE kind = 'agent_run'")
    run = f"/v1/agent/runs/{row['execution_id']}"
    assert (await client.get(run)).json()["result"]["answer"]
    publish(database_url, tenant_a, {"allowed_kbs": ["default"], "allowed_models": "*", "allowed_tools": "*"})
    assert (await client.get(run)).status_code == 404  # the answer of a hidden knowledge base is not served
    assert (await client.get("/v1/agent/runs")).json()["items"] == []
    missing = await client.get(f"/v1/agent/runs/{uuid4()}")
    assert missing.json()["error"]["message"] == (await client.get(run)).json()["error"]["message"]  # same 404


async def test_m1_a_caller_without_audit_read_sees_only_its_own_runs(
    client, make_client, pool, tenant_a, database_url, fake_llm, fake_embeddings,
):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    assert (await client.post("/v1/agent/query", json=AGENT)).status_code == 200
    [row] = await pool.fetch("SELECT execution_id, principal_id FROM jobs WHERE kind = 'agent_run'")
    assert str(row["principal_id"]) == tenant_a.principal_id  # the run records who started it
    _, other_headers = other_principal_headers(database_url, ["agent"])
    other = make_client(other_headers)
    assert (await other.get(f"/v1/agent/runs/{row['execution_id']}")).status_code == 404
    assert (await other.get("/v1/agent/runs")).json()["items"] == []
    _, audit_headers = other_principal_headers(database_url, ["audit:read"])
    audit = make_client(audit_headers)  # an audit reader sees the tenant's runs
    assert (await audit.get(f"/v1/agent/runs/{row['execution_id']}")).status_code == 200
    assert len((await audit.get("/v1/agent/runs")).json()["items"]) == 1
    assert (await client.get(f"/v1/agent/runs/{row['execution_id']}")).status_code == 200  # the owner still does


async def test_m2_the_jobs_routes_hide_agent_runs_of_a_hidden_knowledge_base(
    client, pool, tenant_a, database_url, fake_llm, fake_embeddings,
):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    assert (await client.post("/v1/agent/query", json=AGENT)).status_code == 200
    [row] = await pool.fetch("SELECT id, namespace FROM jobs WHERE kind = 'agent_run'")
    assert row["namespace"] == "legal"
    assert (await client.get(f"/v1/jobs/{row['id']}")).status_code == 200
    publish(database_url, tenant_a, {"allowed_kbs": ["default"], "allowed_models": "*", "allowed_tools": "*"})
    assert (await client.get(f"/v1/jobs/{row['id']}")).status_code == 404
    assert (await client.get("/v1/jobs", params={"kind": "agent_run"})).json()["items"] == []
    assert "legal" not in (await client.get("/v1/jobs")).text  # the hidden knowledge base's name is not served

"""Sprint 009 end to end: an agent run executes in a (fake) sandbox with `AGENT_RUNTIME=openshell`, through the real app,
the real worker, real Postgres and Redis.

The sandbox is `FakeSandboxDriver` (tests/fake_sandbox.py): no real sandbox can run in this container, so this proves the
platform side (run tokens, the gateway routes, the policy checks, the events and the runs API) and the agent program, not
OpenShell itself. `scripts/verify/openshell.sh` is where the real sandbox is checked.

Acceptance covered here: A2 (an authorised task completes), A3 (a direct provider call fails and a network-deny event is
recorded), A4 (a read outside the work directory fails and an event is recorded), A5 (an unauthorised tool argument is a
deny row), and the API half of A6 (sandbox events merged with decisions by execution id).
"""
import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from adapters.registry import build_local_runtime
from core.identity.run_tokens import issue_run_token, revoke_run_tokens
from core.settings import get_settings
from ports import RunSpec, RunState
from tests.db_fixtures import principal_of
from tests.e2e.conftest import adapter_overrides
from tests.e2e.test_gateway_e2e import publish
from tests.e2e.test_search_flow import ingest
from tests.e2e.web_helpers import bearer, key_with
from tests.fake_sandbox import FakeSandboxDriver, blocking_gateway_caller, entry_program
from tests.fakes import SandboxAnswerLLM

GATEWAY = "http://gateway.test:8000"
QUESTION = {"question": "breach notification supervisory authority 72 hours", "namespace": "legal"}
ALLOW_ALL = {"allowed_kbs": "*", "allowed_models": "*", "allowed_tools": "*"}


@pytest.fixture
def sandbox_llm(fake_llm):
    fake_llm.use(SandboxAnswerLLM(agent_namespace="legal"))
    return fake_llm


@pytest.fixture
def openshell_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_runtime", "openshell")
    monkeypatch.setattr(settings, "sandbox_gateway_url", GATEWAY)
    monkeypatch.setattr(settings, "sandbox_wall_seconds", 30)
    return settings


@pytest.fixture
def world():
    """What the program inside the fake sandbox reaches: the app's own HTTP interface, filled in once the app is up."""
    return {}


@pytest_asyncio.fixture
async def app(platform_config, request, openshell_settings, world):
    """The app with its worker running every agent run in the fake sandbox (this module's own `app`)."""
    from api.main import create_app
    from tests import jobs_helpers

    jobs_helpers.OWNER["dsn"] = request.getfixturevalue("database_url")

    driver = FakeSandboxDriver(entry_program(blocking_gateway_caller(lambda: world["client"], lambda: world["loop"])))
    application = create_app(adapter_overrides=adapter_overrides(request), embedded_workers=1, sandbox_driver=driver)
    application.state.sandbox_driver = driver
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
        world["client"] = httpx.AsyncClient(transport=transport, base_url=GATEWAY)
        world["loop"] = asyncio.get_running_loop()
        try:
            yield application
        finally:
            await world["client"].aclose()


@pytest.fixture
def driver(app) -> FakeSandboxDriver:
    return app.state.sandbox_driver


async def run_agent(client, **override):
    return await client.post("/v1/agent/query", json={**QUESTION, **override})


async def decisions_of(pool, execution_id):
    return await pool.fetch("SELECT * FROM gateway_decisions WHERE execution_id = $1 ORDER BY created_at, id", execution_id)


async def execution_of(pool):
    return await pool.fetchval("SELECT execution_id FROM jobs WHERE kind = 'agent_run' ORDER BY created_at DESC LIMIT 1")


async def events_of(pool, execution_id):
    return await pool.fetch("SELECT kind, detail, at FROM sandbox_events WHERE execution_id = $1 ORDER BY at, seq", execution_id)


# ---------------------------------------------------------------------------------------------- A2

async def test_a2_an_authorised_task_completes_in_the_sandbox_and_the_answer_is_the_stored_result(
    app, client, pool, driver, tenant_a, sandbox_llm, fake_embeddings,
):
    await ingest(client)
    resp = await run_agent(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "72 hours" in body["answer"] and body["confidence"] == 0.8 and body["tool_calls_made"] == 1
    assert body["flagged"] is False and [c["source_filename"] for c in body["citations"]] == ["gdpr.md"]
    assert any(step.startswith("Called tool: retrieve_chunks") for step in body["reasoning_steps"])
    execution_id = await execution_of(pool)
    [job] = await pool.fetch("SELECT status, attempts FROM jobs WHERE kind = 'agent_run'")
    assert (job["status"], job["attempts"]) == ("succeeded", 1)
    assert driver.live == set() and driver.destroyed == [str(execution_id)]  # the sandbox is gone
    # what the sandbox was given: one route (the gateway), one work directory, limits, and a token for this run
    [launch] = driver.launches
    assert launch.policy.egress[0].host == "gateway.test" and launch.policy.egress[0].port == 8000 and len(launch.policy.egress) == 1
    assert launch.policy.work_dir == "/sandbox/work" and launch.policy.limits.wall_seconds == 30
    assert launch.env["GATEWAY_URL"] == GATEWAY and launch.env["EXECUTION_ID"] == str(execution_id) and launch.env["RUN_TOKEN"].startswith("grt_")
    assert "OPENAI" not in " ".join(launch.env) and "KEY" not in " ".join(k for k in launch.env if k != "RUN_TOKEN")  # no provider key reaches it


async def test_a2_every_decision_the_run_caused_carries_its_execution_id_including_the_ones_made_over_http_from_the_sandbox(
    app, client, pool, tenant_a, sandbox_llm, fake_embeddings,
):
    await ingest(client)
    assert (await run_agent(client)).status_code == 200
    execution_id = await execution_of(pool)
    rows = await decisions_of(pool, execution_id)
    seen = [(r["action"], r["resource"], r["outcome"]) for r in rows]
    assert seen[0][0] == "agent.run"  # the entry check, in the request
    for expected in (("tool.call", "retrieve_chunks", "allow"), ("kb.read", "legal", "allow")):
        assert expected in seen
    assert sum(1 for a, _, _ in seen if a == "model.invoke") == 3  # entry check, the query embedding, the answer
    assert {r["outcome"] for r in rows} == {"allow"}
    assert await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE execution_id IS NULL AND action <> 'audit.read' AND created_at > (SELECT min(created_at) FROM jobs)") == 0
    # the calls from inside the sandbox are other requests than the entry one, under the same run
    assert len({r["request_id"] for r in rows}) >= 3


async def test_a2_the_run_writes_a_start_and_an_exit_event_and_its_token_is_revoked(app, client, pool, driver, tenant_a, sandbox_llm, fake_embeddings):
    await ingest(client)
    assert (await run_agent(client)).status_code == 200
    execution_id = await execution_of(pool)
    events = await events_of(pool, execution_id)
    assert [e["kind"] for e in events] == ["start", "exit"]
    assert json.loads(events[1]["detail"]) == {"code": 0}
    assert "gateway.test" in json.loads(events[0]["detail"])["host"]
    [token] = await pool.fetch("SELECT revoked_at, expires_at, created_at FROM run_tokens WHERE execution_id = $1", execution_id)
    assert token["revoked_at"] is not None and token["revoked_at"] <= token["expires_at"]
    assert (token["expires_at"] - token["created_at"]).total_seconds() <= 30 + 61  # the TTL is the wall limit and a minute


async def test_a2_usage_is_booked_by_the_gateway_as_each_model_call_is_made_not_reported_by_the_sandbox(
    app, client, pool, tenant_a, sandbox_llm, fake_embeddings,
):
    await ingest(client)
    resp = await run_agent(client)
    assert resp.status_code == 200
    assert await pool.fetchval("SELECT count(*) FROM usage_log WHERE endpoint = '/v1/agent/query'") == 1  # the one model call of the run
    row = await pool.fetchrow("SELECT prompt_tokens, completion_tokens FROM usage_log WHERE endpoint = '/v1/agent/query'")
    assert (row["prompt_tokens"], row["completion_tokens"]) == (40, 9)  # what the model returned, measured at the gateway


# ---------------------------------------------------------------------------------------------- A3, A4

async def test_a3_and_a4_a_direct_provider_call_and_a_read_outside_the_work_directory_fail_and_leave_events(
    app, pool, driver, tenant_a,
):
    from adapters.openshell_runtime import SANDBOX_CHECK_KIND

    runtime = build_local_runtime(get_settings(), runner=None, pool=app.state.db_pool, sandbox_driver=driver)
    handle = await runtime.start(RunSpec(kind=SANDBOX_CHECK_KIND, input={}, tenant_id=UUID(tenant_a.id)))
    result = await runtime.wait(handle.run_id)
    assert result.status.state is RunState.SUCCEEDED
    assert result.output == {
        "provider_call": "failed (ConnectionRefusedError)", "outside_read": "failed (PermissionError)", "outside_path": "/var/lib/dpkg/status"}
    events = await events_of(pool, handle.execution_id)
    kinds = [e["kind"] for e in events]
    assert kinds == ["start", "network_denied", "file_denied", "exit"]
    network, file = json.loads(events[1]["detail"]), json.loads(events[2]["detail"])
    assert (network["host"], network["port"]) == ("api.openai.com", 443)  # A3
    assert file["path"] == "/var/lib/dpkg/status"  # A4


async def test_a3_the_gateway_is_the_one_place_the_sandbox_can_reach(app, pool, driver, tenant_a):
    from adapters.openshell_runtime import SANDBOX_CHECK_KIND
    from tests.fake_sandbox import SandboxProcess

    attempts: list[str] = []

    async def probe(proc: SandboxProcess) -> int:
        for host, port in (("gateway.test", 8000), ("gateway.test", 9999), ("api.groq.com", 443), ("169.254.169.254", 80), ("localhost", 5432)):
            try:
                proc.check_egress(host, port)
                attempts.append(f"{host}:{port} open")
            except ConnectionRefusedError:
                attempts.append(f"{host}:{port} refused")
        proc.stdout(json.dumps({"result": {}}))
        return 0

    driver.program = probe
    runtime = build_local_runtime(get_settings(), runner=None, pool=app.state.db_pool, sandbox_driver=driver)
    handle = await runtime.start(RunSpec(kind=SANDBOX_CHECK_KIND, input={}, tenant_id=UUID(tenant_a.id)))
    await runtime.wait(handle.run_id)
    assert attempts == ["gateway.test:8000 open", "gateway.test:9999 refused", "api.groq.com:443 refused", "169.254.169.254:80 refused", "localhost:5432 refused"]
    denied = [json.loads(e["detail"]) for e in await events_of(pool, handle.execution_id) if e["kind"] == "network_denied"]
    assert [(d["host"], d["port"]) for d in denied] == [("gateway.test", 9999), ("api.groq.com", 443), ("169.254.169.254", 80), ("localhost", 5432)]


# ---------------------------------------------------------------------------------------------- A5

async def test_a5_an_unauthorised_tool_argument_from_the_sandbox_is_a_deny_row_and_the_run_ends_partial(
    app, client, pool, database_url, tenant_a, sandbox_llm, fake_embeddings,
):
    await ingest(client)
    publish(database_url, tenant_a, {**ALLOW_ALL, "tool_arguments": {"retrieve_chunks": {
        "type": "object", "properties": {"top_k": {"type": "integer", "maximum": 3}}, "required": ["query"]}}})
    resp = await run_agent(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["flagged"] is True and "tool_argument_not_allowed" in body["flag_reason"] and body["tool_calls_made"] == 0
    assert "partial" in body["answer"]
    execution_id = await execution_of(pool)
    denies = [r for r in await decisions_of(pool, execution_id) if r["outcome"] == "deny"]
    assert [(r["action"], r["resource"], r["stage"], r["reason"]) for r in denies] == [("tool.call", "retrieve_chunks", "policy", "tool_argument_not_allowed")]
    assert denies[0]["policy_version"] == 1 and denies[0]["execution_id"] == execution_id
    assert not any(r["action"] == "kb.read" for r in await decisions_of(pool, execution_id))  # nothing was read after the deny
    assert sandbox_llm.kinds.count("sandbox_answer") == 0  # and the model was never asked


async def test_a5_the_same_run_succeeds_when_the_policy_allows_the_arguments(app, client, pool, database_url, tenant_a, sandbox_llm, fake_embeddings):
    await ingest(client)
    publish(database_url, tenant_a, {**ALLOW_ALL, "tool_arguments": {"retrieve_chunks": {
        "type": "object", "properties": {"top_k": {"type": "integer", "maximum": 5}, "namespace": {"enum": ["legal"]}}}}})
    body = (await run_agent(client)).json()
    assert body["flagged"] is False and body["tool_calls_made"] == 1


async def test_a5_the_in_process_agent_tools_check_arguments_too(app, client, pool, database_url, tenant_a, sandbox_llm, fake_embeddings):
    """The same policy applies to the MCP and LangGraph tools: the check is in the gateway, not in the sandbox path."""
    from api.agent.tools import make_retrieve_tool
    from gateway import build_context
    from gateway.policy import parse_policy  # noqa: F401

    publish(database_url, tenant_a, {**ALLOW_ALL, "tool_arguments": {"retrieve_chunks": {"type": "object", "properties": {"top_k": {"maximum": 3}}}}})
    ctx = await build_context(app.state.gateway_runtime, principal_of(tenant_a, ("agent",)), "r", "t" * 32)
    ctx.execution_id = uuid4()
    tool = make_retrieve_tool(app.state.adapters)
    out = json.loads(await tool.ainvoke({"query": "x", "namespace": "legal", "top_k": 20}, config={"configurable": {"gateway": ctx}}))
    assert out == {"error": "policy_denied", "reason": "tool_argument_not_allowed"}
    assert ctx.halted == "tool_argument_not_allowed"


# ---------------------------------------------------------------------------------------------- A6, the runs API

async def test_a6_the_runs_api_merges_sandbox_events_with_the_decisions_by_time(
    app, client, make_client, pool, database_url, tenant_a, sandbox_llm, fake_embeddings,
):
    await ingest(client)
    assert (await run_agent(client)).status_code == 200
    execution_id = await execution_of(pool)
    audit = make_client(bearer(key_with(database_url, tenant_a, ["audit:read"])[0]))
    for who in (client, audit):  # the agent that started it, and an audit reader
        run = (await who.get(f"/v1/agent/runs/{execution_id}")).json()
        assert run["status"] == "succeeded" and [e["kind"] for e in run["sandbox_events"]] == ["start", "exit"]
        timeline = run["timeline"]
        assert [i["at"] for i in timeline] == sorted(i["at"] for i in timeline)  # in time order
        sources = [i["source"] for i in timeline]
        assert sources.count("sandbox") == 2 and sources.count("decision") >= 6
        assert sources[0] == "decision" and timeline[-1]["source"] == "sandbox" and timeline[-1]["sandbox"]["kind"] == "exit"
        assert timeline[0]["decision"]["action"] == "agent.run" and next(i for i in timeline if i["source"] == "sandbox")["sandbox"]["kind"] == "start"
        decisions = [i["decision"] for i in timeline if i["source"] == "decision"]
        stored = await decisions_of(pool, execution_id)
        assert {d["id"] for d in decisions} == {str(r["id"]) for r in stored}
        assert all(set(i) == {"source", "at", "decision", "sandbox"} and (i["decision"] is None) != (i["sandbox"] is None) for i in timeline)


async def test_a6_a_denied_network_call_is_in_the_timeline_next_to_the_decisions(app, client, pool, tenant_a, driver, sandbox_llm, fake_embeddings):
    """A deny event from the sandbox and a deny decision from the gateway sit in one ordered list."""
    from tests.fake_sandbox import SandboxProcess

    async def blocked(proc: SandboxProcess) -> int:
        try:
            proc.check_egress("api.openai.com", 443)
        except ConnectionRefusedError:
            pass
        proc.stdout(json.dumps({"result": {"answer": "no network", "denied": "tool_argument_not_allowed", "steps": [], "tool_calls": 0}}))
        return 0

    driver.program = blocked
    assert (await run_agent(client)).status_code == 200
    execution_id = await execution_of(pool)
    run = (await client.get(f"/v1/agent/runs/{execution_id}")).json()
    assert [(i["source"], (i["sandbox"] or {}).get("kind")) for i in run["timeline"] if i["source"] == "sandbox"] == [
        ("sandbox", "start"), ("sandbox", "network_denied"), ("sandbox", "exit")]
    denied = next(i["sandbox"] for i in run["timeline"] if i["source"] == "sandbox" and i["sandbox"]["kind"] == "network_denied")
    assert denied["detail"]["host"] == "api.openai.com"


async def test_a6_a_run_of_another_tenant_or_another_principal_is_not_found(app, client, client_b, make_client, pool, database_url, tenant_a, sandbox_llm, fake_embeddings):
    await ingest(client)
    assert (await run_agent(client)).status_code == 200
    execution_id = await execution_of(pool)
    assert (await client_b.get(f"/v1/agent/runs/{execution_id}")).status_code == 404  # another tenant
    from core.identity.admin import admin_connection, create_key, create_principal

    with admin_connection(database_url) as conn:
        other = create_principal(conn, tenant_a.slug, "service", "someone-else")
        key = create_key(conn, other, ["agent"])
    assert (await make_client(bearer(key.token)).get(f"/v1/agent/runs/{execution_id}")).status_code == 404  # same tenant, not theirs
    # the events table is isolated the same way
    assert await pool.fetchval("SELECT count(*) FROM sandbox_events WHERE execution_id = $1", execution_id) == 2


async def test_a_run_that_never_used_a_sandbox_has_an_empty_event_list_and_still_a_timeline(app, client, pool, tenant_a, driver, sandbox_llm, fake_embeddings):
    await ingest(client)
    assert (await run_agent(client)).status_code == 200
    execution_id = await execution_of(pool)
    await pool.execute("DELETE FROM sandbox_events WHERE execution_id = $1", execution_id)
    run = (await client.get(f"/v1/agent/runs/{execution_id}")).json()
    assert run["sandbox_events"] == [] and {i["source"] for i in run["timeline"]} == {"decision"}


# ---------------------------------------------------------------------------------------------- run tokens over HTTP

async def token_for(app, tenant, execution_id=None, boundary=None, scopes=("agent",), ttl=60):
    principal = principal_of(tenant, scopes)
    from gateway import build_context

    payload = boundary
    if payload is None:
        ctx = await build_context(app.state.gateway_runtime, principal, "r", "t" * 32)
        payload = ctx.boundary.to_payload()
    run = execution_id or uuid4()
    issued = await issue_run_token(app.state.db_pool, principal, run, payload, ttl)
    return run, issued.token


def as_run(make_client, token):
    return make_client(bearer(token))


async def test_a_run_token_works_on_its_own_run_routes(app, make_client, pool, tenant_a, sandbox_llm, fake_embeddings):
    run, token = await token_for(app, tenant_a)
    resp = await as_run(make_client, token).post(f"/v1/sandbox/runs/{run}/model", json={"messages": [{"role": "user", "content": "hello"}]})
    assert resp.status_code == 200 and resp.json()["usage"]["prompt_tokens"] > 0
    row = await pool.fetchrow("SELECT action, resource, outcome, execution_id FROM gateway_decisions WHERE execution_id = $1", run)
    assert (row["action"], row["outcome"], row["execution_id"]) == ("model.invoke", "allow", run)


async def test_a_run_token_is_refused_on_every_route_outside_its_run_and_each_refusal_leaves_a_deny_row(
    app, make_client, pool, tenant_a, sandbox_llm, fake_embeddings,
):
    run, token = await token_for(app, tenant_a)
    other = uuid4()
    client = as_run(make_client, token)
    attempts = [
        ("get", "/v1/agent/runs", None), ("get", "/v1/decisions", None), ("post", "/v1/search", {"query": "x", "namespace": "legal"}),
        ("post", "/v1/agent/query", {"question": "x"}), ("get", "/v1/jobs", None), ("get", "/v1/keys", None), ("get", "/v1/receipts/x", None),
        ("post", f"/v1/sandbox/runs/{other}/model", {"messages": [{"role": "user", "content": "x"}]}),   # another run
        ("post", f"/v1/sandbox/runs/{other}/tools/retrieve_chunks", {"arguments": {"query": "x"}}),
        ("post", f"/v1/sandbox/runs/{run}x/model", {"messages": [{"role": "user", "content": "x"}]}),
    ]
    for method, path, body in attempts:
        resp = await (client.get(path) if method == "get" else client.post(path, json=body))
        assert resp.status_code == 403, (path, resp.status_code)
        assert resp.json()["error"]["code"] == "forbidden" and "token" not in resp.text.lower().replace("run token", "")
    denies = await pool.fetch("SELECT action, outcome, stage, reason FROM gateway_decisions WHERE execution_id = $1", run)
    assert len(denies) == len(attempts) and {(d["outcome"], d["stage"], d["reason"]) for d in denies} == {("deny", "boundary", "run_token_scope")}


async def test_a_run_token_is_refused_after_the_run_revoked_it_and_after_it_expired(app, make_client, pool, tenant_a, sandbox_llm, fake_embeddings):
    body = {"messages": [{"role": "user", "content": "hello"}]}
    run, token = await token_for(app, tenant_a)
    assert (await as_run(make_client, token).post(f"/v1/sandbox/runs/{run}/model", json=body)).status_code == 200
    assert await revoke_run_tokens(app.state.db_pool, UUID(tenant_a.id), run) == 1
    assert (await as_run(make_client, token).post(f"/v1/sandbox/runs/{run}/model", json=body)).status_code == 401
    run2, token2 = await token_for(app, tenant_a)
    await pool.execute("UPDATE run_tokens SET expires_at = $1 WHERE execution_id = $2", datetime(2020, 1, 1, tzinfo=timezone.utc), run2)
    resp = await as_run(make_client, token2).post(f"/v1/sandbox/runs/{run2}/model", json=body)
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "unauthorized"


async def test_a_token_that_is_made_up_or_damaged_is_a_plain_401(app, make_client, tenant_a):
    _, token = await token_for(app, tenant_a)
    for bad in (token[:-2] + "xx", "grt_abcdefgh_" + "z" * 43, "grt_", "grt_abcdefgh_short"):
        resp = await make_client(bearer(bad)).post(f"/v1/sandbox/runs/{uuid4()}/model", json={"messages": [{"role": "user", "content": "x"}]})
        assert resp.status_code == 401 and resp.json()["error"]["message"] == "Missing or invalid credentials"


async def test_a_normal_api_key_cannot_use_the_sandbox_routes(app, client, tenant_a):
    for path, body in ((f"/v1/sandbox/runs/{uuid4()}/model", {"messages": [{"role": "user", "content": "x"}]}),
                       (f"/v1/sandbox/runs/{uuid4()}/tools/list_namespaces", {"arguments": {}})):
        resp = await client.post(path, json=body)
        assert resp.status_code == 403 and resp.json()["error"]["code"] == "forbidden"


async def test_the_boundary_in_the_token_is_the_one_the_run_gets_a_narrower_policy_later_is_not_applied_and_a_wider_one_neither(
    app, make_client, pool, database_url, tenant_a, sandbox_llm, fake_embeddings,
):
    await ingest(make_client(tenant_a.headers("full")))
    from gateway import build_context

    ctx = await build_context(app.state.gateway_runtime, principal_of(tenant_a, ("agent",)), "r", "t" * 32)
    payload = ctx.boundary.to_payload()
    payload["tools"] = ["list_namespaces"]  # the run was accepted with one tool
    run, token = await token_for(app, tenant_a, boundary=payload)
    publish(database_url, tenant_a, ALLOW_ALL)  # a policy published afterwards allows everything: it does not widen the run
    client = as_run(make_client, token)
    denied = await client.post(f"/v1/sandbox/runs/{run}/tools/retrieve_chunks", json={"arguments": {"query": "x", "namespace": "legal"}})
    assert denied.status_code == 403 and "tool_not_allowed" in denied.json()["error"]["message"]
    allowed = await client.post(f"/v1/sandbox/runs/{run}/tools/list_namespaces", json={"arguments": {}})
    assert allowed.status_code == 200 and "legal" in allowed.json()["result"]


async def test_the_models_in_the_boundary_apply_to_the_model_route(app, make_client, pool, tenant_a, sandbox_llm, fake_embeddings):
    from gateway import build_context

    ctx = await build_context(app.state.gateway_runtime, principal_of(tenant_a, ("agent",)), "r", "t" * 32)
    payload = {**ctx.boundary.to_payload(), "models": ["some-other-model"]}
    run, token = await token_for(app, tenant_a, boundary=payload)
    resp = await as_run(make_client, token).post(f"/v1/sandbox/runs/{run}/model", json={"messages": [{"role": "user", "content": "x"}]})
    assert resp.status_code == 403 and "model_not_allowed" in resp.json()["error"]["message"]
    assert await pool.fetchval("SELECT reason FROM gateway_decisions WHERE execution_id = $1", run) == "model_not_allowed"
    assert sandbox_llm.kinds == []  # the model was never called


async def test_the_tool_call_limit_counts_across_the_http_calls_of_one_run(app, make_client, pool, tenant_a, sandbox_llm, fake_embeddings):
    from gateway import build_context

    ctx = await build_context(app.state.gateway_runtime, principal_of(tenant_a, ("agent",)), "r", "t" * 32)
    run, token = await token_for(app, tenant_a, boundary={**ctx.boundary.to_payload(), "max_tool_calls": 2})
    client = as_run(make_client, token)
    statuses = [(await client.post(f"/v1/sandbox/runs/{run}/tools/list_namespaces", json={"arguments": {}})).status_code for _ in range(4)]
    assert statuses == [200, 200, 403, 403]  # each call is its own request: the count comes from the run's decision rows
    reasons = [r["reason"] for r in await pool.fetch("SELECT reason FROM gateway_decisions WHERE execution_id = $1 ORDER BY created_at, id", run)]
    assert reasons == ["allowed", "allowed", "tool_call_limit", "tool_call_limit"]


async def test_bad_input_to_the_sandbox_routes_is_a_validation_error_not_a_server_error(app, make_client, tenant_a, sandbox_llm, fake_embeddings):
    run, token = await token_for(app, tenant_a)
    client = as_run(make_client, token)
    assert (await client.post(f"/v1/sandbox/runs/{run}/tools/no_such_tool", json={"arguments": {}})).status_code == 404
    assert (await client.post(f"/v1/sandbox/runs/{run}/tools/retrieve_chunks", json={"arguments": {"query": 5, "top_k": "many"}})).status_code == 422
    assert (await client.post(f"/v1/sandbox/runs/{run}/model", json={"messages": []})).status_code == 422
    assert (await client.post(f"/v1/sandbox/runs/{run}/model", json={"messages": [{"role": "root", "content": "x"}]})).status_code == 422
    assert (await client.post(f"/v1/sandbox/runs/{run}/model", json={"messages": [{"role": "user", "content": "x" * 20_001}]})).status_code == 422
    assert (await client.post(f"/v1/sandbox/runs/{run}/model", json={"messages": [{"role": "user", "content": "x"}], "max_tokens": 10**6})).status_code == 422


# ---------------------------------------------------------------------------------------------- failure and limits

async def test_a_sandbox_that_cannot_start_fails_the_run_with_a_code_and_still_revokes_the_token(app, client, pool, driver, tenant_a, sandbox_llm, fake_embeddings):
    driver._unavailable = True
    resp = await run_agent(client)
    assert resp.status_code == 500 and resp.json()["error"]["message"] == "Agent execution failed"  # no detail for the caller
    execution_id = await execution_of(pool)
    [job] = await pool.fetch("SELECT status, error_code FROM jobs WHERE kind = 'agent_run'")
    assert (job["status"], job["error_code"]) == ("failed", "agent_run_failed")
    events = await events_of(pool, execution_id)
    assert [e["kind"] for e in events] == ["start", "exit"] and json.loads(events[1]["detail"]) == {"reason": "sandbox_unavailable"}
    assert await pool.fetchval("SELECT revoked_at IS NOT NULL FROM run_tokens WHERE execution_id = $1", execution_id)
    assert driver.destroyed == [str(execution_id)]


async def test_the_token_never_reaches_a_table_a_log_or_an_event(app, client, pool, driver, tenant_a, sandbox_llm, fake_embeddings, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    await ingest(client)
    assert (await run_agent(client)).status_code == 200
    [launch] = driver.launches
    token = launch.env["RUN_TOKEN"]
    secret = token.split("_", 2)[2]
    assert token not in caplog.text and secret not in caplog.text
    for table in ("sandbox_events", "gateway_decisions", "jobs", "usage_log", "run_tokens", "outbox", "processed_events"):
        dump = json.dumps([dict(r) for r in await pool.fetch(f"SELECT * FROM {table}")], default=str)
        assert secret not in dump, table
    assert secret not in json.dumps(driver.launches[0].policy, default=str) and secret not in repr(launch)  # not even in its repr
    answer = (await client.get(f"/v1/agent/runs/{await execution_of(pool)}")).text
    assert secret not in answer


async def test_the_question_text_is_not_in_any_sandbox_event_or_decision_row(app, client, pool, tenant_a, sandbox_llm, fake_embeddings):
    await ingest(client)
    needle = "needle-question-text 72 hours"
    assert (await run_agent(client, question=needle)).status_code == 200
    for table in ("sandbox_events", "gateway_decisions"):
        assert needle not in json.dumps([dict(r) for r in await pool.fetch(f"SELECT * FROM {table}")], default=str)


# ---------------------------------------------------------------------------------------------- QA fixes

async def test_m1_a_fault_on_the_sandbox_routes_is_the_standard_503_not_a_policy_denial(app, make_client, tenant_a, monkeypatch, sandbox_llm, fake_embeddings):
    run, token = await token_for(app, tenant_a)
    client = as_run(make_client, token)
    import gateway.record as record

    async def fail(*a, **k):
        raise RuntimeError("database down")

    monkeypatch.setattr(record, "write_decision", fail)
    for path, body in ((f"/v1/sandbox/runs/{run}/tools/list_namespaces", {"arguments": {}}),
                       (f"/v1/sandbox/runs/{run}/model", {"messages": [{"role": "user", "content": "x"}]})):
        resp = await client.post(path, json=body)
        assert resp.status_code == 503 and resp.json()["error"]["code"] == "service_unavailable", path
    monkeypatch.undo()

    import gateway.stages as stages

    async def boom(boundary, action):
        raise RuntimeError("bug")

    monkeypatch.setattr(stages.ENGINE, "evaluate", boom)
    for path, body in ((f"/v1/sandbox/runs/{run}/tools/list_namespaces", {"arguments": {}}),
                       (f"/v1/sandbox/runs/{run}/model", {"messages": [{"role": "user", "content": "x"}]})):
        resp = await client.post(path, json=body)
        assert resp.status_code == 503, path  # internal_error


async def test_l1_a_leaked_token_writes_one_deny_row_per_path_per_minute_and_is_refused_every_time(app, make_client, pool, tenant_a):
    run, token = await token_for(app, tenant_a)
    client = as_run(make_client, token)
    for _ in range(6):
        assert (await client.get("/v1/agent/runs")).status_code == 403
    assert await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE execution_id = $1", run) == 1
    assert (await client.get("/v1/decisions")).status_code == 403  # another path: its own row
    assert await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE execution_id = $1", run) == 2


async def test_l2_the_runs_api_and_the_stored_result_mark_the_agents_own_fields(app, client, pool, tenant_a, sandbox_llm, fake_embeddings):
    await ingest(client)
    body = (await run_agent(client)).json()
    assert body["agent_reported"] == ["citations", "confidence", "usage"]
    run = (await client.get(f"/v1/agent/runs/{await execution_of(pool)}")).json()
    assert run["result"]["agent_reported"] == ["citations", "confidence", "usage"]
    assert await pool.fetchval("SELECT count(*) FROM usage_log WHERE endpoint = '/v1/agent/query'") == 1  # booked usage is the gateway's


async def test_l6_the_sandbox_routes_refuse_a_run_token_once_its_key_is_revoked(app, make_client, database_url, tenant_a, sandbox_llm, fake_embeddings):
    from core.identity.admin import admin_connection, revoke_key
    from core.identity.store import authenticate_api_key

    principal = await authenticate_api_key(app.state.db_pool, tenant_a.tokens["full"])
    from gateway import build_context

    ctx = await build_context(app.state.gateway_runtime, principal, "r", "t" * 32)
    run = uuid4()
    token = (await issue_run_token(app.state.db_pool, principal, run, ctx.boundary.to_payload(), 60)).token
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert (await as_run(make_client, token).post(f"/v1/sandbox/runs/{run}/model", json=body)).status_code == 200
    with admin_connection(database_url) as conn:
        revoke_key(conn, tenant_a.prefixes["full"])
    assert (await as_run(make_client, token).post(f"/v1/sandbox/runs/{run}/model", json=body)).status_code == 401

"""Gateway follow-up fixes (QA M1-M4, L2-L4) over the real app: HTTP and MCP, real Postgres and Redis, fake LLM.

Each test asserts the fake LLM and embedding call counts and the `gateway_decisions` rows, not only the status.
"""
from uuid import UUID

import litellm

from tests.e2e.test_gateway_e2e import AGENT, ALL, LoopingLLM, _mcp_call, error_of, publish, rows, summary
from tests.e2e.test_search_flow import QUERY, ingest

GEN_MODEL = "gemini/gemini-3.5-flash-lite"


def break_policy(dsn, tenant):
    """An active policy row that cannot be parsed: the boundary then denies every action for the tenant."""
    import psycopg2

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant.id,))
        cur.execute("INSERT INTO policies (tenant_id, version, document, created_by, active) "
                    "VALUES (%s, 1, '{\"allowed_kbs\": 5}', 'x', TRUE)", (tenant.id,))
    conn.close()


# ------------------------------------------------------------------ M1: MCP applies the tool and model allowlists

async def test_m1_mcp_tool_with_an_empty_tool_allowlist_is_a_tool_error_with_no_embedding_and_a_deny_row(
        app, client, pool, tenant_a, database_url, fake_llm, fake_embeddings):
    publish(database_url, tenant_a, {**ALL, "allowed_tools": []})

    reply = await _mcp_call(app, client, tenant_a.headers("full"), "search_documents", {"query": "retention", "namespace": "legal"})
    assert reply["result"]["isError"] is True
    assert "tool_not_allowed" in reply["result"]["content"][0]["text"]
    assert fake_embeddings.calls == [] and fake_llm.calls == []
    assert summary(await rows(pool, tenant_a, "AND outcome = 'deny'")) == [
        ("tool.call", "search_documents", "deny", "policy", "tool_not_allowed")]

    for name, arguments in (("list_namespaces", {}), ("get_ingestion_status", {"namespace": "legal"}), ("get_cost_summary", {}),
                            ("multi_namespace_search", {"query": "retention"})):
        reply = await _mcp_call(app, client, tenant_a.headers("full"), name, arguments)
        assert reply["result"]["isError"] is True, name
        assert "tool_not_allowed" in reply["result"]["content"][0]["text"], name
    denied = await rows(pool, tenant_a, "AND outcome = 'deny'")
    assert len(denied) == 5 and {(r["action"], r["reason"]) for r in denied} == {("tool.call", "tool_not_allowed")}
    assert {r["resource"] for r in denied} == {"search_documents", "list_namespaces", "get_ingestion_status", "get_cost_summary", "multi_namespace_search"}
    assert fake_embeddings.calls == []


async def test_m1_multi_namespace_search_with_explicit_namespaces_still_checks_its_own_tool_name(
        app, client, pool, tenant_a, database_url, fake_llm, fake_embeddings):
    publish(database_url, tenant_a, {**ALL, "allowed_tools": ["search_documents"]})
    reply = await _mcp_call(app, client, tenant_a.headers("full"), "multi_namespace_search",
                            {"query": "retention", "namespaces": ["legal"]})
    assert reply["result"]["isError"] is True
    assert "tool_not_allowed" in reply["result"]["content"][0]["text"]
    assert fake_embeddings.calls == [] and fake_llm.calls == []
    assert summary(await rows(pool, tenant_a, "AND outcome = 'deny'")) == [
        ("tool.call", "multi_namespace_search", "deny", "policy", "tool_not_allowed")]


async def test_m1_mcp_search_gates_model_invoke_by_model_and_by_token_cap(app, client, pool, tenant_a, database_url, fake_llm, fake_embeddings):
    embedding_model = (await _embedding_model())
    publish(database_url, tenant_a, {**ALL, "allowed_models": [GEN_MODEL]})  # the embedding model is not listed
    reply = await _mcp_call(app, client, tenant_a.headers("full"), "search_documents", {"query": "retention", "namespace": "legal"})
    assert reply["result"]["isError"] is True and "model_not_allowed" in reply["result"]["content"][0]["text"]
    assert fake_embeddings.calls == []
    denied = await rows(pool, tenant_a, "AND outcome = 'deny'")
    assert summary(denied) == [("model.invoke", embedding_model, "deny", "policy", "model_not_allowed")]
    # the tool call and the KB read before it were allowed and recorded
    assert [(r["action"], r["resource"]) for r in await rows(pool, tenant_a, "AND outcome = 'allow' AND resource IS NOT NULL")] == [
        ("tool.call", "search_documents"), ("kb.read", "legal")]

    publish(database_url, tenant_a, {**ALL, "max_tokens_per_request": 3})
    reply = await _mcp_call(app, client, tenant_a.headers("full"), "search_documents", {"query": "x" * 200, "namespace": "legal"})
    assert reply["result"]["isError"] is True and "token_limit" in reply["result"]["content"][0]["text"]
    assert fake_embeddings.calls == []


async def _embedding_model() -> str:
    from config import LLM_CONFIG

    return str(LLM_CONFIG["embedding_model"])


# ------------------------------------------------------------------ M2: a failed decision write fails closed over HTTP

async def test_m2_with_insert_revoked_on_gateway_decisions_search_is_503_decision_unrecorded_and_nothing_is_called(
        client, pool, tenant_a, fake_llm, fake_embeddings):
    await ingest(client)
    embedded_before = len(fake_embeddings.calls)
    await pool.execute("REVOKE INSERT ON gateway_decisions FROM gap_app")
    try:
        err = error_of(await client.post("/v1/search", json=QUERY), 503, "decision_unrecorded")
        assert "unavailable" in err["message"]
        error_of(await client.post("/v1/agent/query", json=AGENT), 503, "decision_unrecorded")
        assert fake_llm.calls == [] and len(fake_embeddings.calls) == embedded_before
    finally:
        await pool.execute("GRANT INSERT ON gateway_decisions TO gap_app")
    rows_before = len(await rows(pool, tenant_a))
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200  # grant restored: works again
    assert len(await rows(pool, tenant_a)) > rows_before


# ------------------------------------------------------------------ M3: /v1/config hides KBs the policy denies

async def test_m3_config_lists_only_the_knowledge_bases_the_policy_allows(client, client_b, pool, tenant_a, tenant_b, database_url):
    publish(database_url, tenant_a, {**ALL, "allowed_kbs": ["legal"]})
    resp = await client.get("/v1/config")
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["namespaces"]) == {"legal"}

    other = await client_b.get("/v1/config")  # tenant B has no policy: all of its own knowledge bases
    assert set(other.json()["namespaces"]) == {"legal", "kyc_aml", "default"}

    publish(database_url, tenant_a, {**ALL, "allowed_kbs": []})
    assert (await client.get("/v1/config")).json()["namespaces"] == {}
    assert {(r["action"], r["outcome"]) for r in await rows(pool, tenant_a)} == {("kb.read", "allow")}


# ------------------------------------------------------------------ M4: feedback, quality report and analytics are gated

async def test_m4_feedback_quality_report_and_analytics_write_decision_rows(client, pool, tenant_a):
    assert (await client.post("/v1/feedback", json={"request_id": "r1", "endpoint": "/v1/search", "rating": "up"})).status_code == 201
    assert (await client.get("/v1/quality-report")).status_code == 200
    assert (await client.get("/v1/analytics/summary")).status_code == 200
    assert summary(await rows(pool, tenant_a)) == [
        ("feedback.write", None, "allow", "allow", "allowed"),
        ("analytics.read", None, "allow", "allow", "allowed"),
        ("analytics.read", None, "allow", "allow", "allowed"),
    ]
    assert await pool.fetchval("SELECT count(*) FROM feedback") == 1


async def test_m4_a_deny_policy_blocks_feedback_quality_report_and_analytics(client, pool, tenant_a, database_url):
    break_policy(database_url, tenant_a)
    err = error_of(await client.post("/v1/feedback", json={"request_id": "r1", "endpoint": "/v1/search", "rating": "up"}), 403, "policy_denied")
    assert err["message"] == "Denied by policy (reason: policy_unavailable)"
    error_of(await client.get("/v1/quality-report"), 403, "policy_denied")
    error_of(await client.get("/v1/analytics/summary"), 403, "policy_denied")
    assert await pool.fetchval("SELECT count(*) FROM feedback") == 0  # nothing was written
    assert summary(await rows(pool, tenant_a)) == [
        ("feedback.write", None, "deny", "policy", "policy_unavailable"),
        ("analytics.read", None, "deny", "policy", "policy_unavailable"),
        ("analytics.read", None, "deny", "policy", "policy_unavailable"),
    ]


async def test_m4_the_scope_map_grants_feedback_to_query_and_analytics_to_kb_read(make_client, pool, tenant_a):
    query_only, reader = make_client(tenant_a.headers("query_only")), make_client(tenant_a.headers("reader"))
    assert (await query_only.post("/v1/feedback", json={"request_id": "r", "endpoint": "/v1/search", "rating": "down"})).status_code == 201
    assert (await reader.get("/v1/analytics/summary")).status_code == 200
    assert (await reader.get("/v1/quality-report")).status_code == 200
    assert (await reader.post("/v1/feedback", json={"request_id": "r", "endpoint": "/v1/search", "rating": "up"})).status_code == 403
    assert [(r["action"], r["outcome"], r["reason"]) for r in await rows(pool, tenant_a)] == [
        ("feedback.write", "allow", "allowed"), ("analytics.read", "allow", "allowed"), ("analytics.read", "allow", "allowed"),
        ("kb.read", "deny", "missing_scope")]  # a missing `query` scope is recorded under the kb.read action
    assert await pool.fetchval("SELECT count(*) FROM feedback") == 1


# ------------------------------------------------------------------ L2: a missing scope leaves a deny row

async def test_l2_a_missing_scope_is_403_and_writes_a_deny_row_with_no_work_done(make_client, pool, tenant_a, fake_llm, fake_embeddings):
    reader = make_client(tenant_a.headers("reader"))      # kb:read only
    query_only = make_client(tenant_a.headers("query_only"))
    resp = await reader.post("/v1/search", json=QUERY)
    assert resp.status_code == 403 and resp.json()["error"]["message"] == "Missing required scope: query"
    assert (await query_only.post("/v1/ingest", params={"namespace": "legal"},
                                  files={"file": ("a.md", b"# A\n\ntext\n", "text/markdown")})).status_code == 403
    assert (await reader.post("/v1/agent/query", json=AGENT)).status_code == 403

    got = await rows(pool, tenant_a)
    assert [(r["action"], r["outcome"], r["stage"], r["reason"]) for r in got] == [
        ("kb.read", "deny", "boundary", "missing_scope"),
        ("kb.write", "deny", "boundary", "missing_scope"),
        ("agent.run", "deny", "boundary", "missing_scope"),
    ]
    assert all(r["input_hash"] is None and r["tenant_id"] == UUID(tenant_a.id) for r in got)
    assert fake_llm.calls == [] and fake_embeddings.calls == []


# ------------------------------------------------------------------ L3: completion max_tokens counts against the cap

async def test_l3_the_completion_max_tokens_count_against_max_tokens_per_request(client, pool, tenant_a, database_url, fake_llm, fake_embeddings):
    from api.services.llm import GENERATION_MAX_TOKENS
    from gateway.estimate import estimate_tokens

    await ingest(client)
    embedded_before = len(fake_embeddings.calls)
    estimate = estimate_tokens(QUERY["query"], GENERATION_MAX_TOKENS)
    assert estimate > GENERATION_MAX_TOKENS > estimate_tokens(QUERY["query"])  # the input alone would fit under the cap below

    publish(database_url, tenant_a, {**ALL, "max_tokens_per_request": GENERATION_MAX_TOKENS})
    err = error_of(await client.post("/v1/search", json=QUERY), 403, "policy_denied")
    assert err["message"] == "Denied by policy (reason: token_limit)"
    assert fake_llm.calls == [] and len(fake_embeddings.calls) == embedded_before
    denied = await rows(pool, tenant_a, "AND outcome = 'deny'")
    assert summary(denied) == [("model.invoke", GEN_MODEL, "deny", "policy", "token_limit")]

    publish(database_url, tenant_a, {**ALL, "max_tokens_per_request": estimate})  # exactly the estimate fits
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200
    assert fake_llm.kinds == ["synthesis"]


async def test_l3_the_agent_run_counts_its_completion_tokens_too(client, pool, tenant_a, database_url, fake_llm, fake_embeddings):
    from api.agent.models import AGENT_MAX_TOKENS

    publish(database_url, tenant_a, {**ALL, "max_tokens_per_request": AGENT_MAX_TOKENS})
    error_of(await client.post("/v1/agent/query", json=AGENT), 403, "policy_denied")
    assert fake_llm.calls == [] and fake_embeddings.calls == []
    assert summary(await rows(pool, tenant_a, "AND outcome = 'deny'")) == [("model.invoke", GEN_MODEL, "deny", "policy", "token_limit")]


# ------------------------------------------------------------------ L4: no verifier call after a halt

async def test_l4_no_verifier_call_after_a_halt(client, pool, tenant_a, database_url, monkeypatch, fake_embeddings):
    looping = LoopingLLM(agent_namespace="legal")
    monkeypatch.setattr(litellm, "acompletion", looping.acompletion)
    await ingest(client)
    publish(database_url, tenant_a, {**ALL, "max_tool_calls": 1})

    resp = await client.post("/v1/agent/query", json={**AGENT, "enable_verifier": True})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["flagged"] is True and "tool_call_limit" in data["flag_reason"]
    assert "verifier" not in looping.kinds  # the run was cut short: no model call spent on verifying a partial answer
    assert looping.kinds.count("agent_tool_call") == 2 and "synthesis" in looping.kinds
    model_rows = await rows(pool, tenant_a, "AND action = 'model.invoke'")
    generation = [r for r in model_rows if r["resource"] == GEN_MODEL]
    assert len(generation) == len(looping.kinds) + 1  # one per LLM call, plus the route's entry check; none for a verifier


# ------------------------------------------------------------------ L1: every recorded reason is in the catalogue

async def test_every_reason_the_gateway_records_is_in_the_catalogue(client, pool, tenant_a, database_url, monkeypatch, fake_llm, fake_embeddings):
    """Run allowed and denied calls through the real app, then read the reasons back from gateway_decisions.

    The static scan reads string literals only. This one checks what the gateway really wrote.
    """
    from gateway.reasons import REASONS

    await ingest(client)
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200  # allowed
    error_of(await client.get("/v1/overview"), 403, "forbidden")  # missing scope (the full key has no audit:read)

    publish(database_url, tenant_a, {**ALL, "allowed_kbs": ["legal"], "blocked_terms": ["project zephyr"], "max_tokens_per_request": 5})
    error_of(await client.post("/v1/search", json={**QUERY, "namespace": "kyc_aml"}), 403, "policy_denied")  # kb_not_allowed
    error_of(await client.post("/v1/search", json={**QUERY, "query": "tell me about project zephyr"}), 400, "query_blocked")  # guardrail
    error_of(await client.post("/v1/search", json={**QUERY, "query": "breach " * 10}), 403, "policy_denied")  # token_limit

    publish(database_url, tenant_a, {**ALL, "allowed_models": ["some/other-model"]})
    error_of(await client.post("/v1/search", json=QUERY), 403, "policy_denied")  # model_not_allowed

    publish(database_url, tenant_a, {**ALL, "allowed_tools": []})
    resp = await client.post("/v1/agent/query", json=AGENT)  # tool_not_allowed: a flagged partial answer, not an error
    assert resp.status_code == 200 and "tool_not_allowed" in resp.json()["flag_reason"]

    looping = LoopingLLM(agent_namespace="legal")
    monkeypatch.setattr(litellm, "acompletion", looping.acompletion)
    publish(database_url, tenant_a, {**ALL, "max_tool_calls": 1})
    assert (await client.post("/v1/agent/query", json={**AGENT, "enable_verifier": False})).status_code == 200  # tool_call_limit

    recorded = {r["reason"] for r in await pool.fetch("SELECT DISTINCT reason FROM gateway_decisions WHERE tenant_id = $1", UUID(tenant_a.id))}
    # Prove the run really covered the paths, so the subset check below is not vacuous.
    assert {"allowed", "missing_scope", "kb_not_allowed", "query_blocked", "token_limit", "model_not_allowed", "tool_call_limit"} <= recorded
    assert recorded <= set(REASONS), sorted(recorded - set(REASONS))

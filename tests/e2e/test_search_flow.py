"""End-to-end: ingest -> search -> documents -> feedback -> analytics, through the real app."""
import re
from datetime import datetime, timezone

from tests.e2e.conftest import eventually

GDPR = b"# GDPR breach notification\n\nA personal data breach must be notified to the supervisory authority within 72 hours.\n"
GDPR_V2 = b"# GDPR breach notification\n\nA personal data breach must be notified to the supervisory authority within 48 hours.\n"
QUERY = {"query": "breach notification supervisory authority 72 hours", "namespace": "legal", "rerank": False}


async def ingest(client, content=GDPR, name="gdpr.md", namespace="legal"):
    return await client.post("/v1/ingest", params={"namespace": namespace},
                             files={"file": (name, content, "text/markdown")})


async def test_ingest_search_documents_feedback_analytics(client, pool, fake_llm, fake_embeddings):
    # 1. ingest
    resp = await ingest(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "gdpr.md"
    assert body["namespace"] == "legal"
    assert body["status"] == "new"
    assert body["total_chunks"] >= 1
    assert body["chunks_deleted"] == 0
    assert len(body["content_hash"]) == 64
    assert await pool.fetchval("SELECT count(*) FROM documents") == body["total_chunks"]

    # 2. search answers from the ingested file and cites it
    resp = await client.post("/v1/search", json=QUERY)
    assert resp.status_code == 200
    data = resp.json()
    assert "within 72 hours" in data["answer"]
    assert data["confidence"] == 0.9
    assert data["total_results"] == 1
    assert data["results"][0]["document_id"] == "gdpr.md"
    assert "(from gdpr.md," in fake_llm.calls[0]["messages"][0]["content"]  # real filename reaches the prompt
    assert data["results"][0]["namespace"] == "legal"
    assert data["results"][0]["metadata"] == {"chunk_index": 0}
    assert data["flagged"] is False
    assert resp.headers["X-Cache"] == "MISS"
    tokens_in = int(resp.headers["X-Tokens-In"])
    assert tokens_in > 0
    assert resp.headers["X-Tokens-Out"] == "7"
    query_id = resp.headers["X-Query-ID"]
    assert query_id == resp.headers["X-Request-ID"]
    assert fake_llm.kinds == ["synthesis"]
    assert "[chunk_0]" in fake_llm.calls[0]["messages"][0]["content"]

    # 3. the usage row is written (fire-and-forget) with real values
    import config

    row = await eventually(lambda: pool.fetchrow("SELECT * FROM usage_log WHERE endpoint = '/v1/search'"))
    assert row["request_id"] == query_id
    assert row["namespace"] == "legal"
    assert row["model"] == config.LLM_CONFIG["model"]
    assert resp.headers["X-Cost-USD"] == f"{float(row['cost_usd']):.6f}"
    assert row["prompt_tokens"] == tokens_in
    assert row["completion_tokens"] == 7

    # 4. documents lists it
    docs = (await client.get("/v1/documents", params={"namespace": "legal"})).json()
    assert docs["count"] == 1
    assert docs["documents"][0]["document_id"] == "gdpr.md"
    assert docs["documents"][0]["source_filename"] == "gdpr.md"
    assert docs["documents"][0]["chunk_count"] == body["total_chunks"]
    assert docs["documents"][0]["content_hash"] == body["content_hash"]
    assert (await client.get("/v1/documents", params={"namespace": "kyc_aml"})).json() == {"documents": [], "count": 0}

    # 5. feedback is accepted and stored against the query id
    resp = await client.post("/v1/feedback", json={"request_id": query_id, "endpoint": "/v1/search", "rating": "up"})
    assert resp.status_code == 201
    assert resp.json() == {"status": "recorded"}
    fb = await pool.fetchrow("SELECT request_id, endpoint, rating FROM feedback")
    assert (fb["request_id"], fb["endpoint"], fb["rating"]) == (query_id, "/v1/search", "up")

    # 6. analytics reflects the usage rows
    summary = (await client.get("/v1/analytics/summary", params={"days": 1})).json()
    by_endpoint = {e["endpoint"]: e["requests"] for e in summary["by_endpoint"]}
    assert by_endpoint == {"/v1/ingest": 1, "/v1/search": 1}
    assert summary["total_requests"] == 2
    assert summary["total_tokens"] == tokens_in + 7
    assert summary["by_day"][0]["date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    quality = (await client.get("/v1/quality-report")).json()
    assert quality["by_endpoint"] == [
        {"endpoint": "/v1/search", "thumbs_up": 1, "thumbs_down": 0, "total": 1, "approval_rate": 1.0}
    ]


async def test_second_identical_search_is_an_exact_cache_hit(client, fake_llm, fake_embeddings):
    await ingest(client)
    first = await client.post("/v1/search", json=QUERY)
    assert first.headers["X-Cache"] == "MISS"
    await eventually(lambda: _cache_written(client))  # cache write is fire-and-forget

    second = await client.post("/v1/search", json=QUERY)

    assert second.headers["X-Cache"] == "HIT"
    assert second.headers["X-Cache-Type"] == "exact"
    assert second.headers["X-Cost-USD"] == "0.000000"
    assert second.json() == first.json()
    assert fake_llm.kinds == ["synthesis"]  # the LLM was not called a second time


async def _cache_written(client) -> bool:
    from api.services.cache import get_redis

    r = await get_redis()
    return bool([k async for k in r.scan_iter(match="cache:v*")])


async def test_search_in_empty_namespace_is_404_in_standard_format(client, fake_llm, fake_embeddings):
    # `legal` is one of the tenant's knowledge bases, but nothing is ingested into it.
    resp = await client.post("/v1/search", json={"query": "anything at all", "namespace": "legal", "rerank": False})
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "not_found"
    assert "legal" in err["message"]
    assert err["request_id"] == resp.headers["X-Request-ID"]
    assert fake_llm.calls == []


async def test_reingest_unchanged_then_changed(client, pool, fake_llm, fake_embeddings):
    first = (await ingest(client)).json()
    assert first["status"] == "new"
    calls_after_first = len(fake_embeddings.calls)

    same = (await ingest(client)).json()
    assert same["status"] == "unchanged"
    assert same["total_chunks"] == 0
    assert same["content_hash"] == first["content_hash"]
    assert len(fake_embeddings.calls) == calls_after_first
    assert await pool.fetchval("SELECT count(*) FROM documents") == first["total_chunks"]

    changed = (await ingest(client, GDPR_V2)).json()
    assert changed["status"] == "updated"
    assert changed["chunks_deleted"] == first["total_chunks"]
    assert changed["content_hash"] != first["content_hash"]
    contents = " ".join(r["content"] for r in await pool.fetch("SELECT content FROM documents"))
    assert "48 hours" in contents
    assert "72 hours" not in contents
    assert await pool.fetchval("SELECT count(*) FROM document_registry") == 1

    answer = (await client.post("/v1/search", json=QUERY)).json()
    assert "48 hours" in answer["answer"]
    assert "72 hours" not in answer["answer"]


async def test_agent_query_runs_the_graph_with_the_fake_llm(client, fake_llm, fake_embeddings):
    fake_llm.agent_namespace = "legal"
    await ingest(client)

    resp = await client.post("/v1/agent/query", json={"question": "breach notification supervisory authority", "namespace": "legal"})

    assert resp.status_code == 200
    data = resp.json()
    assert fake_llm.kinds == ["agent_tool_call", "agent_final", "synthesis", "verifier"]
    assert data["tool_calls_made"] == 1
    assert data["reasoning_steps"][0].startswith("Called tool: retrieve_chunks(")
    assert "'namespace': 'legal'" in data["reasoning_steps"][0]
    assert "within 72 hours" in data["answer"]
    assert [c["document_id"] for c in data["citations"]] == ["gdpr.md"]
    assert [c["source_filename"] for c in data["citations"]] == ["gdpr.md"]
    assert data["verified"] is True
    assert data["verification_notes"] == "Grounded in the chunks."
    assert data["confidence"] == 0.9
    assert re.fullmatch(r"\d+", resp.headers["X-Tokens-In"])
    assert resp.headers["X-Query-ID"] == resp.headers["X-Request-ID"]


async def test_agent_query_without_documents_says_so(client, fake_llm, fake_embeddings):
    fake_llm.agent_namespace = "legal"
    resp = await client.post("/v1/agent/query", json={"question": "anything", "namespace": "legal"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "I could not find relevant documents to answer this question."
    assert resp.json()["citations"] == []


async def test_search_cost_header_equals_logged_cost_for_a_priced_model(client, pool, fake_llm, fake_embeddings, monkeypatch):
    import config

    monkeypatch.setitem(config.MODEL_PRICING, config.LLM_CONFIG["model"], {"input": 1000.0, "output": 2000.0})
    import api.middleware.finops as finops

    monkeypatch.setattr(finops, "MODEL_PRICING", config.MODEL_PRICING)
    await ingest(client)

    resp = await client.post("/v1/search", json=QUERY)

    tokens_in = int(resp.headers["X-Tokens-In"])
    expected = tokens_in * 1000.0 / 1_000_000 + 7 * 2000.0 / 1_000_000
    assert expected > 0
    assert float(resp.headers["X-Cost-USD"]) == round(expected, 6)
    row = await eventually(lambda: pool.fetchrow("SELECT * FROM usage_log WHERE endpoint = '/v1/search'"))
    assert row["model"] == config.LLM_CONFIG["model"]
    assert float(row["cost_usd"]) == expected

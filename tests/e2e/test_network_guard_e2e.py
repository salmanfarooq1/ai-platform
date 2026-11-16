"""A11: through the real app, an unfaked provider call becomes a 502 naming the guard, never a network call."""
from tests.e2e.test_search_flow import QUERY, ingest


async def test_network_guard_stops_unfaked_embedding_in_the_app(client, json_logs):
    resp = await client.post("/v1/search", json=QUERY)  # no fake_embeddings fixture requested
    assert resp.status_code == 502
    err = resp.json()["error"]
    assert err["code"] == "bad_gateway"
    assert err["message"] == "Embedding provider failed"
    assert "litellm." not in err["message"]
    assert any("litellm.aembedding" in line.get("message", "") for line in json_logs())


async def test_network_guard_stops_unfaked_llm_in_the_app(client, fake_embeddings, json_logs):
    assert (await ingest(client)).status_code == 200  # embeddings are faked
    resp = await client.post("/v1/search", json=QUERY)  # but no fake_llm
    assert resp.status_code == 502
    err = resp.json()["error"]
    assert err["message"] == "LLM provider failed"
    assert "litellm." not in err["message"]
    assert any("litellm.acompletion" in line.get("message", "") for line in json_logs())

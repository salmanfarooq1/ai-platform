"""A11: through the real app, an unfaked provider call becomes a 502 naming the guard, never a network call."""
from tests.e2e.test_search_flow import QUERY, ingest


async def test_network_guard_stops_unfaked_embedding_in_the_app(client):
    resp = await client.post("/v1/search", json=QUERY)  # no fake_embeddings fixture requested
    assert resp.status_code == 502
    err = resp.json()["error"]
    assert err["code"] == "bad_gateway"
    assert "Embedding provider failed" in err["message"]
    assert "litellm.aembedding" in err["message"]


async def test_network_guard_stops_unfaked_llm_in_the_app(client, fake_embeddings):
    assert (await ingest(client)).status_code == 200  # embeddings are faked
    resp = await client.post("/v1/search", json=QUERY)  # but no fake_llm
    assert resp.status_code == 502
    err = resp.json()["error"]
    assert "LLM provider failed" in err["message"]
    assert "litellm.acompletion" in err["message"]

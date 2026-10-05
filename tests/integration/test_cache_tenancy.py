"""Exact and semantic caches are tenant-scoped in real Redis (requirement 11)."""
from uuid import uuid4

import pytest

from api.services.cache import (
    get_cached_response,
    semantic_cache_lookup,
    semantic_cache_store,
    set_cached_response,
)
from tests.fakes import fake_embedding

A, B = uuid4(), uuid4()
QUERY = "breach notification supervisory authority 72 hours"
NEAR = "breach notification supervisory authority 72 hours please"
RESPONSE_A = {"answer": "tenant A private answer", "results": []}


@pytest.fixture
async def semantic_cache(redis_cache, redis_client):
    """The Redis cache adapter with its semantic index created, as at app startup."""
    await redis_cache.ensure_semantic_index()
    return redis_cache


async def test_exact_cache_is_isolated_per_tenant(semantic_cache):
    await set_cached_response(semantic_cache, A, QUERY, "legal", 5, RESPONSE_A, "hybrid", False)

    assert await get_cached_response(semantic_cache, A, QUERY, "legal", 5, "hybrid", False) == RESPONSE_A
    assert await get_cached_response(semantic_cache, B, QUERY, "legal", 5, "hybrid", False) is None
    assert await get_cached_response(semantic_cache, str(A), QUERY, "legal", 5, "hybrid", False) == RESPONSE_A


async def test_semantic_cache_is_isolated_per_tenant_including_near_duplicates(semantic_cache):
    await semantic_cache_store(semantic_cache, A, QUERY, "legal", fake_embedding(QUERY), RESPONSE_A, "hybrid", False, 5)

    # sanity: the near-duplicate really is a semantic hit for the owner, so the miss for B means something
    assert await semantic_cache_lookup(semantic_cache, A, NEAR, "legal", fake_embedding(NEAR), "hybrid", False, 5) == RESPONSE_A
    assert await semantic_cache_lookup(semantic_cache, A, QUERY, "legal", fake_embedding(QUERY), "hybrid", False, 5) == RESPONSE_A
    # the same query and the near-duplicate, for another tenant: miss
    assert await semantic_cache_lookup(semantic_cache, B, QUERY, "legal", fake_embedding(QUERY), "hybrid", False, 5) is None
    assert await semantic_cache_lookup(semantic_cache, B, NEAR, "legal", fake_embedding(NEAR), "hybrid", False, 5) is None


async def test_both_tenants_can_hold_their_own_entry_for_the_same_query(semantic_cache):
    await set_cached_response(semantic_cache, A, QUERY, "legal", 5, {"answer": "from A"}, "hybrid", False)
    await set_cached_response(semantic_cache, B, QUERY, "legal", 5, {"answer": "from B"}, "hybrid", False)
    await semantic_cache_store(semantic_cache, A, QUERY, "legal", fake_embedding(QUERY), {"answer": "from A"}, "hybrid", False, 5)
    await semantic_cache_store(semantic_cache, B, QUERY, "legal", fake_embedding(QUERY), {"answer": "from B"}, "hybrid", False, 5)

    assert (await get_cached_response(semantic_cache, A, QUERY, "legal", 5, "hybrid", False))["answer"] == "from A"
    assert (await get_cached_response(semantic_cache, B, QUERY, "legal", 5, "hybrid", False))["answer"] == "from B"
    assert (await semantic_cache_lookup(semantic_cache, A, NEAR, "legal", fake_embedding(NEAR), "hybrid", False, 5))["answer"] == "from A"
    assert (await semantic_cache_lookup(semantic_cache, B, NEAR, "legal", fake_embedding(NEAR), "hybrid", False, 5))["answer"] == "from B"


async def test_stored_entries_carry_the_tenant_as_an_indexed_tag(semantic_cache, redis_client):
    await semantic_cache_store(semantic_cache, A, QUERY, "legal", fake_embedding(QUERY), RESPONSE_A, "hybrid", False, 5)
    [key] = [k async for k in redis_client.scan_iter(match="semcache:*")]
    assert await redis_client.hget(key, "tenant_id") == str(A)
    info = str(await redis_client.execute_command("FT.INFO", "idx:semantic_cache"))
    assert "tenant_id" in info


async def test_a_pre_tenant_index_is_recreated_and_old_entries_never_match(redis_cache, redis_client):
    """An index built before Sprint 003 has no tenant_id field. Startup must replace it, and entries
    written under it (no tenant_id) must not be served to anyone."""
    await redis_client.execute_command(
        "FT.CREATE", "idx:semantic_cache", "ON", "HASH", "PREFIX", "1", "semcache:", "SCHEMA",
        "embedding", "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", "768", "DISTANCE_METRIC", "COSINE",
        "response", "TEXT", "query", "TEXT", "namespace", "TAG", "retrieval_mode", "TAG", "rerank", "TAG",
        "top_k", "NUMERIC", "created_at", "NUMERIC",
    )
    import numpy as np

    await redis_client.hset("semcache:legacy", mapping={
        "embedding": np.array(fake_embedding(QUERY), dtype=np.float32).tobytes(), "response": '{"answer": "old"}',
        "query": QUERY, "namespace": "legal", "retrieval_mode": "hybrid", "rerank": "0", "top_k": "5", "created_at": 1,
    })
    try:
        assert "tenant_id" not in str(await redis_client.execute_command("FT.INFO", "idx:semantic_cache"))

        await redis_cache.ensure_semantic_index()

        assert "tenant_id" in str(await redis_client.execute_command("FT.INFO", "idx:semantic_cache"))
        assert await semantic_cache_lookup(redis_cache, A, QUERY, "legal", fake_embedding(QUERY), "hybrid", False, 5) is None
    finally:
        await redis_client.delete("semcache:legacy")


async def test_creating_the_index_twice_keeps_it(semantic_cache, redis_client):
    await semantic_cache.ensure_semantic_index()
    await semantic_cache.ensure_semantic_index()
    assert "tenant_id" in str(await redis_client.execute_command("FT.INFO", "idx:semantic_cache"))


async def test_the_semantic_cache_is_isolated_per_embedding_model(semantic_cache):
    """A response cached under one embedding model is never served for another (Sprint 006)."""
    await semantic_cache_store(semantic_cache, A, QUERY, "legal", fake_embedding(QUERY), RESPONSE_A, "hybrid", False, 5, "model/one")

    assert await semantic_cache_lookup(semantic_cache, A, QUERY, "legal", fake_embedding(QUERY), "hybrid", False, 5, "model/one") == RESPONSE_A
    assert await semantic_cache_lookup(semantic_cache, A, QUERY, "legal", fake_embedding(QUERY), "hybrid", False, 5, "model/two") is None

"""Resolved model identity isolates persisted vectors and cache entries."""
from uuid import UUID, uuid4

import pytest

from adapters.redis_cache import _to_bytes
from api.services.cache import cache_key, get_cached_response, set_cached_response
from ports import ChunkRow

pytestmark = pytest.mark.integration


async def test_two_digests_never_mix(knowledge_store, tenant_a, redis_cache, redis_client):
    tenant_id = UUID(tenant_a.id)
    alias = "ollama/nomic-embed-text"
    digest_a = "sha256:" + "a" * 64
    digest_b = "sha256:" + "b" * 64
    identity_a, identity_b = f"{alias}@{digest_a}", f"{alias}@{digest_b}"
    vector = [0.0] * 768
    vector[0] = 1.0
    await knowledge_store.insert_chunks(
        tenant_id, "digest-a.md", "legal", [ChunkRow("digest A source", vector)],
        embedding_model=identity_a, embedding_dim=768,
    )
    await knowledge_store.insert_chunks(
        tenant_id, "digest-b.md", "legal", [ChunkRow("digest B source", vector)],
        embedding_model=identity_b, embedding_dim=768,
    )

    results = await knowledge_store.search_vector(
        tenant_id, vector, "legal", 10, embedding_model=identity_b, embedding_dim=768,
    )
    assert [hit["document_id"] for hit in results] == ["digest-b.md"]
    assert await knowledge_store.count_stale_vectors(identity_b, 768) == 1

    response = {"answer": "digest A"}
    await set_cached_response(
        redis_cache, tenant_id, "identity question", "legal", 5, response,
        embedding_model=identity_a,
    )
    exact_key = cache_key(tenant_id, "identity question", "legal", 5, embedding_model=identity_a)
    semantic_key = f"cache:semantic:{uuid4().hex}"
    try:
        assert await get_cached_response(
            redis_cache, tenant_id, "identity question", "legal", 5, embedding_model=identity_b,
        ) is None
        await redis_cache.ensure_semantic_index()
        await redis_client.hset(semantic_key, mapping={
            "embedding": _to_bytes(vector), "response": '{"answer":"digest A"}',
            "query": "identity question", "tenant_id": str(tenant_id), "embedding_model": identity_a,
            "namespace": "legal", "retrieval_mode": "hybrid", "top_k": "5", "created_at": 1,
        })
        await redis_client.expire(semantic_key, 60)
        assert await redis_cache.semantic_lookup(
            tenant_id, "legal", vector, embedding_model=identity_b, retrieval_mode="hybrid",
            top_k=5, min_similarity=0.8,
        ) is None
    finally:
        await redis_client.delete(exact_key, semantic_key)


async def test_rows_without_digest_are_stale(knowledge_store, tenant_a):
    tenant_id = UUID(tenant_a.id)
    alias = "ollama/nomic-embed-text"
    identity = f"{alias}@sha256:{'c' * 64}"
    vector = [0.0] * 768
    vector[0] = 1.0
    await knowledge_store.insert_chunks(
        tenant_id, "legacy.md", "legal", [ChunkRow("legacy provenance source", vector)],
        embedding_model=alias, embedding_dim=768,
    )

    found = await knowledge_store.search_vector(
        tenant_id, vector, "legal", 10, embedding_model=identity, embedding_dim=768,
    )
    assert found == []
    assert await knowledge_store.count_stale_vectors(identity, 768) == 1

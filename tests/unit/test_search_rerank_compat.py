"""The removed rerank request option remains accepted but has no effect."""
from uuid import uuid4

import pytest

from adapters.redis_cache import SEMANTIC_INDEX, RedisCache
from api.models.schemas import SearchRequest
from api.services.cache import cache_key


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deprecated_flag_is_ignored():
    schema = SearchRequest.model_json_schema()
    assert schema["properties"]["rerank"]["deprecated"] is True

    enabled = SearchRequest(query="retention policy", rerank=True)
    disabled = SearchRequest(query="retention policy", rerank=False)
    assert enabled.query == disabled.query
    tenant_id = uuid4()
    assert cache_key(tenant_id, enabled.query, "legal", 5, embedding_model="alias@sha256:x") == cache_key(
        tenant_id, disabled.query, "legal", 5, embedding_model="alias@sha256:x",
    )
    assert cache_key(tenant_id, enabled.query, "legal", 5, embedding_model="alias@sha256:x").startswith("cache:")
    assert SEMANTIC_INDEX == "idx:semantic_cache"

    class SearchStub:
        queries: list[str] = []

        async def execute_command(self, *args):
            self.queries.append(args[1])
            return [0]

    cache = RedisCache("redis://localhost:1", 2)
    stub = SearchStub()
    cache._client = stub
    await cache.semantic_lookup(
        tenant_id, "legal", [0.0, 1.0], embedding_model="alias@sha256:x", retrieval_mode="hybrid",
        top_k=5, min_similarity=0.8,
    )
    assert "@rerank" not in stub.queries[0]

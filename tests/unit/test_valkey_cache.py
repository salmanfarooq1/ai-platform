"""Valkey Search compatibility without weakening cache outage semantics."""
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError, ResponseError

from adapters.redis_cache import RedisCache
from ports.cache import CacheUnavailable


def adapter(client):
    cache = RedisCache("redis://localhost:6379", 3)
    cache._client = client
    return cache


@pytest.mark.parametrize("message", [
    "Index already exists", "Index idx:semantic_cache in database 0 already exists",
])
async def test_already_exists_text_of_both_servers(message):
    client = AsyncMock()
    client.execute_command.side_effect = [ResponseError(message), ["tenant_id", "embedding_model"]]
    await adapter(client).ensure_semantic_index()
    assert client.execute_command.await_count == 2


async def test_unexpected_index_error_is_not_tolerated():
    client = AsyncMock()
    client.execute_command.side_effect = ResponseError("unknown command FT.CREATE")
    with pytest.raises(CacheUnavailable):
        await adapter(client).ensure_semantic_index()


async def test_index_metadata_outage_raises_the_port_failure_type():
    client = AsyncMock()
    client.execute_command.side_effect = [ResponseError("Index in database 0 already exists"), RedisError("unavailable")]
    with pytest.raises(CacheUnavailable):
        await adapter(client).ensure_semantic_index()


async def test_schema_has_no_unsearched_text_fields():
    client = AsyncMock()
    await adapter(client).ensure_semantic_index()
    command = client.execute_command.call_args.args
    assert "VECTOR" in command and "TAG" in command and "NUMERIC" in command
    assert "response" not in command and "query" not in command and "TEXT" not in command


async def test_knn_returns_unindexed_fields_without_sortby():
    client = AsyncMock()
    client.execute_command.return_value = [1, "semcache:1", ["response", "answer", "score", "0.01", "query", "question"]]
    hit = await adapter(client).semantic_lookup(
        "tenant", "kb", [1.0, 0.0, 0.0], embedding_model="model", retrieval_mode="hybrid",
        rerank=False, top_k=5, min_similarity=0.8,
    )
    assert hit is not None and hit.response == "answer" and hit.query == "question"
    command = client.execute_command.call_args.args
    assert "SORTBY" not in command
    position = command.index("RETURN")
    assert command[position:position + 5] == ("RETURN", "3", "response", "score", "query")

"""Cache and counters on Redis Stack (moved from `api/services/cache.py`, behaviour unchanged).

Covers the exact and semantic response cache, the rate limit and daily budget counters, and web sessions.
Every `redis.RedisError` becomes `CacheUnavailable`, so callers never see the SDK.
"""
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID, uuid4

import numpy as np
import redis.asyncio as redis
from redis.exceptions import RedisError, ResponseError

from ports.cache import CacheUnavailable, SemanticHit

logger = logging.getLogger("adapters.redis_cache")

SEMANTIC_INDEX = "idx:semantic_cache"
NO_MODEL = "-"  # an empty TAG value is a RediSearch syntax error: callers that pass no model share this one

# Characters that RediSearch tag syntax treats as delimiters; escape each with a backslash so tag filter
# values are literal. The safe chars for a tag value are [a-zA-Z0-9_-].
_TAG_SPECIAL = (',', '.', '<', '>', '{', '}', '[', ']', '(', ')',
                '|', '!', '@', '#', '$', '%', '^', '&', '*', '-',
                '+', '=', ' ', '/', ':', ';')
_TAG_ESCAPE = str.maketrans({c: '\\' + c for c in _TAG_SPECIAL})

T = TypeVar("T")


def _to_bytes(embedding: list[float]) -> bytes:
    """Convert list[float] to FLOAT32 bytes for Redis vector storage."""
    return np.array(embedding, dtype=np.float32).tobytes()


async def _guard(call: Callable[[], Awaitable[T]]) -> T:
    try:
        return await call()
    except RedisError as exc:
        raise CacheUnavailable(str(exc)) from exc


class RedisCache:
    def __init__(self, url: str, embedding_dim: int, max_connections: int = 10) -> None:
        # decode_responses: returns str not bytes so we don't need .decode(). Typed Any: redis-py's stubs type
        # every reply as `bytes | str | None` (it is sync and async in one), which says nothing useful here.
        self._client: Any = redis.from_url(url, decode_responses=True, max_connections=max_connections)
        self._dim = embedding_dim

    async def get(self, key: str) -> str | None:
        value: Any = await _guard(lambda: self._client.get(key))
        return None if value is None else str(value)

    async def set(self, key: str, value: str, *, ttl: int) -> None:
        # SET with ex= is one atomic operation: setting and expiring in different commands is not atomic and
        # can leak memory if the process crashes between the two calls.
        await _guard(lambda: self._client.set(key, value, ex=ttl))

    async def incr(self, key: str, amount: int = 1, *, ttl: int | None = None) -> int:
        async def run() -> int:
            total = int(await self._client.incrby(key, amount))
            if ttl is not None and total == amount:
                await self._client.expire(key, ttl)
            return total

        return await _guard(run)

    async def expire(self, key: str, ttl: int) -> None:
        await _guard(lambda: self._client.expire(key, ttl))

    async def delete(self, key: str) -> None:
        await _guard(lambda: self._client.delete(key))

    async def ping(self) -> None:
        await _guard(lambda: self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()

    # --- semantic cache ---

    async def _ft_create(self) -> None:
        await self._client.execute_command(
            "FT.CREATE", SEMANTIC_INDEX,
            "ON", "HASH",
            "PREFIX", "1", "semcache:",
            "SCHEMA",
            "embedding", "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", str(self._dim),
                "DISTANCE_METRIC", "COSINE",
            "response", "TEXT",
            "query", "TEXT",
            "tenant_id", "TAG",
            "embedding_model", "TAG",
            "namespace", "TAG",
            "retrieval_mode", "TAG",
            "rerank", "TAG",
            "top_k", "NUMERIC",
            "created_at", "NUMERIC",
        )

    async def ensure_semantic_index(self) -> None:
        """
        Create the RediSearch HNSW vector index for the semantic cache.
        Idempotent: safe to call on every restart (including multi-worker). Only the specific
        'Index already exists' error is tolerated; everything else raises so startup fails loudly.

        An index created before Sprint 003 has no tenant_id field, and one created before Sprint 006 has no
        embedding_model field; a query that filters on a missing field would error. Such an index is dropped (without deleting the cached hashes, which have no tenant_id and
        so never match a tenant filter) and created again.
        """
        try:
            await self._ft_create()
            logger.info("[cache] Semantic cache index created")
        except ResponseError as e:
            if "Index already exists" in str(e):
                info = await self._client.execute_command("FT.INFO", SEMANTIC_INDEX)
                if "tenant_id" in str(info) and "embedding_model" in str(info):
                    logger.debug("[cache] Semantic cache index already exists, skipping (idempotent)")
                else:
                    logger.warning("[cache] Semantic cache index lacks a field the queries filter on; recreating it")
                    await self._client.execute_command("FT.DROPINDEX", SEMANTIC_INDEX)
                    await self._ft_create()
            else:
                # Real Redis misconfiguration: wrong DIM, unsupported Redis version, etc.
                logger.error(f"[cache] Unexpected error creating semantic cache index: {e}")
                raise CacheUnavailable(str(e)) from e
        except RedisError as e:
            logger.error(f"[cache] Failed to create semantic cache index: {e}")
            raise CacheUnavailable(str(e)) from e

    async def semantic_lookup(
        self,
        tenant_id: UUID | str,
        namespace: str,
        embedding: list[float],
        *,
        embedding_model: str,
        retrieval_mode: str,
        rerank: bool,
        top_k: int,
        min_similarity: float,
    ) -> SemanticHit | None:
        """KNN search in the Redis vector index for a semantically similar cached response."""
        vec_bytes = _to_bytes(embedding)

        # The KNN pre-filter covers all retrieval config dimensions, so hybrid and bm25 results, or rerank
        # on and off, never contaminate each other. All pre-filters sit inside ONE paren group so RediSearch
        # parses them as AND-ed conditions before the =>[KNN ...] combinator (separate groups are an implicit
        # OR in Dialect 2). Numeric range for top_k: @top_k:[n n] selects the exact value.
        tenant_tag = str(tenant_id).translate(_TAG_ESCAPE)
        model_tag = (embedding_model or NO_MODEL).translate(_TAG_ESCAPE)
        ns_tag = namespace.translate(_TAG_ESCAPE)
        mode_tag = retrieval_mode.translate(_TAG_ESCAPE)
        rerank_str = str(int(rerank))

        filter_query = (
            f"(@tenant_id:{{{tenant_tag}}}"
            f" @embedding_model:{{{model_tag}}}"
            f" @namespace:{{{ns_tag}}}"
            f" @retrieval_mode:{{{mode_tag}}}"
            f" @rerank:{{{rerank_str}}}"
            f" @top_k:[{top_k} {top_k}])"
            f"=>[KNN 1 @embedding $vec AS score]"
        )

        results: Any = await _guard(lambda: self._client.execute_command(
            "FT.SEARCH", SEMANTIC_INDEX,
            filter_query,
            "PARAMS", "2", "vec", vec_bytes,
            "RETURN", "3", "response", "score", "query",
            "SORTBY", "score",
            "DIALECT", "2",
        ))

        # results format varies by Redis protocol (RESP2 = list, RESP3 = dict)
        if isinstance(results, dict):
            if results.get("total_results", 0) == 0 or not results.get("results"):
                return None
            field_dict = results["results"][0].get("extra_attributes", {})
        else:
            if not results or results[0] == 0:
                return None
            fields = results[2]
            field_dict = {fields[i]: fields[i + 1] for i in range(0, len(fields), 2)}

        distance = float(field_dict.get("score", 1.0))
        similarity = 1 - distance
        if similarity < min_similarity:
            return None
        return SemanticHit(response=field_dict["response"], similarity=similarity, query=field_dict.get("query", ""))

    async def semantic_store(
        self,
        tenant_id: UUID | str,
        namespace: str,
        embedding: list[float],
        response: str,
        *,
        query: str,
        embedding_model: str,
        retrieval_mode: str,
        rerank: bool,
        top_k: int,
        ttl: int,
    ) -> None:
        """Store the query embedding and response in a Redis HASH for semantic indexing.

        A pipeline (MULTI/EXEC) makes HSET + EXPIRE atomic. Without it, a crash between the two commands
        leaves a permanent entry with no TTL: a Redis memory leak.
        """
        key = f"semcache:{uuid4().hex}"

        async def run() -> None:
            async with self._client.pipeline(transaction=True) as pipe:
                await pipe.hset(key, mapping={
                    "embedding": _to_bytes(embedding),
                    "response": response,
                    "query": query,
                    "tenant_id": str(tenant_id),
                    "embedding_model": embedding_model or NO_MODEL,
                    "namespace": namespace,
                    "retrieval_mode": retrieval_mode,
                    "rerank": str(int(rerank)),    # Redis TAG fields must be strings
                    "top_k": str(top_k),           # Redis NUMERIC as string
                    "created_at": int(time.time()),
                })
                await pipe.expire(key, ttl)
                await pipe.execute()

        await _guard(run)

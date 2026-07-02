import hashlib
import json
import redis.asyncio as redis
import numpy as np
from uuid import uuid4
import time
import litellm
from config import CACHE_CONFIG, LLM_CONFIG

CACHE_TTL_SECONDS = 3600  # 1 hour

# --- Connection management ---

_redis_pool: redis.Redis | None = None

async def get_redis() -> redis.Redis:
    """Return shared Redis connection. Created once at startup."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            CACHE_CONFIG["url"],
            decode_responses=True,  # returns str not bytes — no .decode() needed
            max_connections=10,
        )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


async def redis_health() -> str:
    """Returns 'ok' or error string."""
    try:
        r = await get_redis()
        await r.ping()
        return "ok"
    except Exception as e:
        return f"error: {e}"


# --- Cache key ---

def cache_key(query: str, namespace: str, top_k: int) -> str:
    """
    Deterministic cache key from query parameters.

    Normalize first — "What is AI?" and "what is ai?" must hit
    the same cache entry. Without normalization, identical semantic
    queries generate different keys — 0% hit rate in practice.

    SHA-256 truncated to 16 hex chars (64 bits):
    - Prevents raw query text leaking into Redis key space (PII concern)
    - Collision probability negligible for a cache use case
    - Prefix 'cache:' namespaces keys — when you add sessions or rate
      limits to Redis later, they won't collide with cache entries
    """
    normalized = query.lower().strip()
    raw = f"{normalized}:{namespace}:{top_k}"
    hash_hex = hashlib.sha256(raw.encode()).hexdigest()
    return f"cache:{hash_hex[:16]}"


# --- Cache-aside operations ---

async def get_cached_response(query: str, namespace: str, top_k: int) -> dict | None:
    """
    Cache-aside read.

    Returns parsed dict on HIT, None on MISS or any Redis failure.
    Cache is never in the correctness path — None is always safe,
    caller just falls through to the full pipeline.
    """
    try:
        r = await get_redis()
        key = cache_key(query, namespace, top_k)
        value = await r.get(key)

        if value is None:
            return None  # explicit miss

        return json.loads(value)  # already str because decode_responses=True

    except redis.RedisError:
        return None  # degrade gracefully — cache miss, not a crash


async def set_cached_response(
    query: str,
    namespace: str,
    top_k: int,
    response: dict,
) -> None:
    """
    Cache-aside write. Fire-and-forget.

    SET with ex= is one atomic operation — never SET then EXPIRE separately.
    If the process crashes between two calls, the key never expires.
    That is a Redis memory leak that only shows up under load.
    """
    try:
        r = await get_redis()
        key = cache_key(query, namespace, top_k)
        await r.set(key, json.dumps(response), ex=CACHE_TTL_SECONDS)

    except redis.RedisError:
        pass  # fire-and-forget — response already returned to client

# --- Semantic Cache ---

SEMANTIC_CACHE_THRESHOLD = 0.65
SEMANTIC_CACHE_TTL = 3600

async def create_semantic_cache_index() -> None:
    """
    Create RediSearch HNSW vector index for semantic cache.
    """
    try:
        r = await get_redis()
        await r.execute_command(
            "FT.CREATE", "idx:semantic_cache",
            "ON", "HASH",
            "PREFIX", "1", "semcache:",
            "SCHEMA",
            "embedding", "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", "768",
                "DISTANCE_METRIC", "COSINE",
            "response", "TEXT",
            "query", "TEXT",
            "namespace", "TAG",
            "created_at", "NUMERIC",
        )
        print("[cache] Semantic cache index created")
    except Exception:
        pass  # Index already exists — idempotent, safe to ignore

async def embed_query(query: str) -> list[float]:
    """Embed a single query string using LiteLLM."""
    response = await litellm.aembedding(
        model=LLM_CONFIG["embedding_model"],
        input=[query]
    )
    return response.data[0]["embedding"]

def _to_bytes(embedding: list[float]) -> bytes:
    """Convert list[float] to FLOAT32 bytes for Redis vector storage."""
    return np.array(embedding, dtype=np.float32).tobytes()

async def semantic_cache_lookup(
    query: str,
    namespace: str,
    query_embedding: list[float],
) -> dict | None:
    """KNN search in Redis vector index for semantically similar cached response."""
    try:
        r = await get_redis()
        vec_bytes = _to_bytes(query_embedding)

        results = await r.execute_command(
            "FT.SEARCH", "idx:semantic_cache",
            f"(@namespace:{{{namespace}}})=>[KNN 1 @embedding $vec AS score]",
            "PARAMS", "2", "vec", vec_bytes,
            "RETURN", "3", "response", "score", "query",
            "SORTBY", "score",
            "DIALECT", "2",
        )

        # results format varies by Redis protocol (RESP2 = list, RESP3 = dict)
        if isinstance(results, dict):
            if results.get("total_results", 0) == 0 or not results.get("results"):
                return None
            field_dict = results["results"][0].get("extra_attributes", {})
        else:
            if not results or results[0] == 0:
                return None
            fields = results[2]
            field_dict = {fields[i]: fields[i+1] for i in range(0, len(fields), 2)}

        distance = float(field_dict.get("score", 1.0))
        similarity = 1 - distance

        if similarity < SEMANTIC_CACHE_THRESHOLD:
            return None

        print(f"[semantic cache] HIT — similarity={similarity:.4f} for query='{field_dict.get('query', '')}'")
        return json.loads(field_dict["response"])

    except redis.RedisError:
        return None

async def semantic_cache_store(
    query: str,
    namespace: str,
    query_embedding: list[float],
    response: dict,
) -> None:
    """Store query embedding + response in Redis HASH for semantic indexing."""
    try:
        r = await get_redis()
        key = f"semcache:{uuid4().hex}"

        await r.hset(key, mapping={
            "embedding": _to_bytes(query_embedding),
            "response": json.dumps(response),
            "query": query,
            "namespace": namespace,
            "created_at": int(time.time()),
        })
        await r.expire(key, SEMANTIC_CACHE_TTL)

    except redis.RedisError:
        pass  # fire-and-forget
    
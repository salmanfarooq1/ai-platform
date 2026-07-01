import hashlib
import json
import redis.asyncio as redis
from config import CACHE_CONFIG

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
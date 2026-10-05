import hashlib
import json
import logging
from uuid import UUID

from ports import CachePort, CacheUnavailable

logger = logging.getLogger("api.cache")

CACHE_TTL_SECONDS = 3600  # 1 hour

# Bump this whenever the shape of SearchResponse changes (e.g. new field, type change).
# Old cache entries with a different version prefix become unreachable and expire via TTL.
# This prevents Pydantic validation errors when deserializing stale cached responses.
CACHE_SCHEMA_VERSION = 2  # 2: keys carry tenant_id (Sprint 003)


async def cache_health(cache: CachePort) -> str:
    """Returns 'ok' or error string."""
    try:
        await cache.ping()
        return "ok"
    except Exception as e:
        return f"error: {e}"


# --- Cache key ---

def cache_key(
    tenant_id: UUID | str,
    query: str,
    namespace: str,
    top_k: int,
    retrieval_mode: str = "hybrid",
    rerank: bool = True,
    embedding_model: str = "",
) -> str:
    """
    Deterministic cache key from query parameters.

    Normalize first — "What is AI?" and "what is ai?" must hit
    the same cache entry. Without normalization, identical semantic
    queries generate different keys — 0% hit rate in practice.

    SHA-256 truncated to 16 hex chars (64 bits):
    - Prevents raw query text leaking into Redis key space (PII concern)

    tenant_id is part of the hashed key, so one tenant can never read another's cached answer
    (row-level security cannot protect Redis).

    embedding_model is part of the hashed key when given (Sprint 006): an answer retrieved with one embedding
    model is never served after the active model changes.

    CACHE_SCHEMA_VERSION prefix:
    - Bumping the version makes all old entries unreachable without a FLUSHALL.
    - Old entries expire naturally via TTL (1 hour). Zero-downtime schema migration.
    """
    normalized = query.lower().strip()
    raw = f"{tenant_id}:{normalized}:{namespace}:{top_k}:{retrieval_mode}:{rerank}"
    if embedding_model:
        raw += f":{embedding_model}"
    hash_hex = hashlib.sha256(raw.encode()).hexdigest()
    return f"cache:v{CACHE_SCHEMA_VERSION}:{hash_hex[:16]}"


# --- Cache-aside operations ---

async def get_cached_response(
    cache: CachePort,
    tenant_id: UUID | str,
    query: str,
    namespace: str,
    top_k: int,
    retrieval_mode: str = "hybrid",
    rerank: bool = True,
    embedding_model: str = "",
) -> dict | None:
    """
    Cache-aside read.

    Returns parsed dict on HIT, None on MISS or any cache failure.
    """
    try:
        key = cache_key(tenant_id, query, namespace, top_k, retrieval_mode, rerank, embedding_model)
        value = await cache.get(key)

        if value is None:
            return None  # explicit miss

        parsed: dict = json.loads(value)
        return parsed

    except CacheUnavailable as e:
        logger.warning(f"[cache] Redis unavailable on exact lookup: {e}. Degrading gracefully.")
        return None  # degrade gracefully — cache miss, not a crash


async def set_cached_response(
    cache: CachePort,
    tenant_id: UUID | str,
    query: str,
    namespace: str,
    top_k: int,
    response: dict,
    retrieval_mode: str = "hybrid",
    rerank: bool = True,
    embedding_model: str = "",
) -> None:
    """
    Cache-aside write. Fire-and-forget.

    One atomic SET with a TTL (see `RedisCache.set`).
    """
    try:
        key = cache_key(tenant_id, query, namespace, top_k, retrieval_mode, rerank, embedding_model)
        await cache.set(key, json.dumps(response), ttl=CACHE_TTL_SECONDS)

    except CacheUnavailable as e:
        logger.warning(f"[cache] Redis unavailable on exact cache write: {e}. Response already returned.")

# --- Semantic Cache ---

SEMANTIC_CACHE_THRESHOLD = 0.65
SEMANTIC_CACHE_TTL = 3600


async def semantic_cache_lookup(
    cache: CachePort,
    tenant_id: UUID | str,
    query: str,
    namespace: str,
    query_embedding: list[float],
    retrieval_mode: str = "hybrid",
    rerank: bool = True,
    top_k: int = 5,
    embedding_model: str = "",
) -> dict | None:
    """KNN search for a semantically similar cached response."""
    try:
        hit = await cache.semantic_lookup(
            tenant_id, namespace, query_embedding,
            embedding_model=embedding_model, retrieval_mode=retrieval_mode, rerank=rerank, top_k=top_k,
            min_similarity=SEMANTIC_CACHE_THRESHOLD,
        )
        if hit is None:
            return None
        logger.info(f"[cache] Semantic HIT — similarity={hit.similarity:.4f} query='{hit.query}'")
        parsed: dict = json.loads(hit.response)
        return parsed

    except CacheUnavailable as e:
        logger.warning(f"[cache] Redis unavailable on semantic lookup: {e}. Degrading gracefully.")
        return None


async def semantic_cache_store(
    cache: CachePort,
    tenant_id: UUID | str,
    query: str,
    namespace: str,
    query_embedding: list[float],
    response: dict,
    retrieval_mode: str = "hybrid",
    rerank: bool = True,
    top_k: int = 5,
    embedding_model: str = "",
) -> None:
    """Store the query embedding and response for semantic indexing (best effort)."""
    try:
        await cache.semantic_store(
            tenant_id, namespace, query_embedding, json.dumps(response),
            query=query, embedding_model=embedding_model, retrieval_mode=retrieval_mode, rerank=rerank,
            top_k=top_k, ttl=SEMANTIC_CACHE_TTL,
        )

    except CacheUnavailable as e:
        logger.warning(f"[cache] Redis unavailable on semantic cache store: {e}.")

"""Cache port: a string key-value store with TTLs, counters and a semantic (vector) lookup.

Redis is derived state (strict rule 6): losing it must never lose data. Every method raises
`CacheUnavailable` when the backend cannot be reached; callers choose to degrade or to deny.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class CacheUnavailable(Exception):
    """The cache backend failed."""


@dataclass(frozen=True)
class SemanticHit:
    response: str
    similarity: float
    query: str


class CachePort(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, *, ttl: int) -> None: ...

    async def incr(self, key: str, amount: int = 1, *, ttl: int | None = None) -> int:
        """Add `amount` and return the new total. `ttl` is applied when the call created the key."""
        ...

    async def expire(self, key: str, ttl: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def ping(self) -> None: ...

    async def ensure_semantic_index(self) -> None: ...

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
    ) -> SemanticHit | None: ...

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
    ) -> None: ...

    async def close(self) -> None: ...

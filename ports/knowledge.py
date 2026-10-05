"""Knowledge store port: chunks, documents, the document registry and knowledge bases.

Every method takes the tenant. The one exception is `count_stale_vectors`, a platform-level count with no row
content, used by the health endpoint.
"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

Hit = dict[str, Any]  # id, document_id, content, metadata, source_filename and one score key (bm25_score or vector_score)


@dataclass
class ChunkRow:
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    namespace: str
    source_filename: str | None
    content_hash: str
    chunk_count: int
    last_ingested_at: datetime


class KnowledgeStore(Protocol):
    async def kb_exists(self, tenant_id: UUID, slug: str) -> bool: ...

    async def list_knowledge_bases(self, tenant_id: UUID) -> dict[str, str]:
        """slug to description, ordered by slug."""
        ...

    async def search_bm25(
        self, tenant_id: UUID, query: str, namespace: str, limit: int, *, embedding_model: str, embedding_dim: int
    ) -> list[Hit]:
        """Full-text search. Like the vector search it only covers rows embedded with the active model and
        dimension: a row from another model is stale and takes part in no search."""
        ...

    async def search_vector(
        self,
        tenant_id: UUID,
        embedding: list[float],
        namespace: str,
        limit: int,
        *,
        embedding_model: str,
        embedding_dim: int,
        min_score: float = 0.0,
    ) -> list[Hit]:
        """Only rows embedded with `embedding_model` at `embedding_dim` are compared; others are ignored."""
        ...

    async def insert_chunks(
        self,
        tenant_id: UUID,
        document_id: str,
        namespace: str,
        chunks: Sequence[ChunkRow],
        *,
        embedding_model: str,
        embedding_dim: int,
    ) -> None: ...

    async def delete_document(self, tenant_id: UUID, document_id: str, namespace: str) -> int:
        """Delete every chunk of the document. Returns the number of chunks deleted."""
        ...

    async def document_status(self, tenant_id: UUID, document_id: str, namespace: str, content_hash: str) -> str:
        """`new`, `unchanged` or `updated`, from the registry."""
        ...

    async def register_document(
        self,
        tenant_id: UUID,
        document_id: str,
        namespace: str,
        content_hash: str,
        chunk_count: int,
        source_filename: str,
    ) -> None: ...

    async def list_documents(
        self, tenant_id: UUID, namespace: str | None, visible_kbs: Sequence[str] | None
    ) -> list[DocumentRecord]:
        """Registry rows, newest first. `visible_kbs` None means every knowledge base."""
        ...

    async def count_stale_vectors(self, embedding_model: str, embedding_dim: int) -> int:
        """Chunks, across tenants, embedded with another model or dimension than the active one."""
        ...

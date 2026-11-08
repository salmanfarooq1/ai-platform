"""Knowledge store on Postgres with pgvector (moved, SQL unchanged except the provenance filter and columns).

Moved from: `api/services/retriever.py` (retrieve_bm25, retrieve_vector), `core/ingestion/lifecycle.py`
(check_document_status, delete_document_chunks, register_document), `core/database/bulk_ops.py` (bulk_insert),
`api/routers/docs.py` (the registry listing), `api/auth.py` (require_kb) and the knowledge-base reads of the
agent and MCP tools. Every query runs through `tenant_connection`, so row-level security applies.
"""
import json
import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from core.database.tenant import DbPool, tenant_connection
from ports.knowledge import ChunkRow, DocumentRecord, Hit

logger = logging.getLogger("adapters.pg_knowledge")

BM25_OR_THRESHOLD = 5  # queries with 5 or more words switch AND to OR


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        parsed: dict[str, Any] = json.loads(raw)
        return parsed
    out: dict[str, Any] = raw or {}
    return out


class PgKnowledgeStore:
    def __init__(self, pool: DbPool) -> None:
        self._pool = pool

    async def kb_exists(self, tenant_id: UUID, slug: str) -> bool:
        async with tenant_connection(self._pool, tenant_id) as conn:
            return bool(await conn.fetchval("SELECT 1 FROM knowledge_bases WHERE slug = $1", slug))

    async def list_knowledge_bases(self, tenant_id: UUID) -> dict[str, str]:
        async with tenant_connection(self._pool, tenant_id) as conn:
            rows = await conn.fetch("SELECT slug, description FROM knowledge_bases ORDER BY slug")
        return {r["slug"]: r["description"] for r in rows}

    async def search_bm25(
        self, tenant_id: UUID, query: str, namespace: str, limit: int, *, embedding_model: str, embedding_dim: int
    ) -> list[Hit]:
        # Compatibility name: this is Postgres full-text ts_rank, not true BM25.
        word_count = len(query.split())
        use_or_mode = word_count >= BM25_OR_THRESHOLD

        async with tenant_connection(self._pool, tenant_id) as conn:
            if use_or_mode:
                tsq = await conn.fetchval(
                    "SELECT replace(plainto_tsquery('english', $1)::text, '&', '|')::tsquery", query
                )
            else:
                tsq = await conn.fetchval(
                    "SELECT plainto_tsquery('english', $1)", query
                )

            if not str(tsq):
                return []

            rows = await conn.fetch(
                """
                SELECT id, document_id, content, metadata,
                       ts_rank(fts_vector, $1) AS bm25_score
                FROM documents
                WHERE tenant_id = $4 AND namespace = $2 AND fts_vector @@ $1
                  AND embedding_model = $5 AND embedding_dim = $6
                ORDER BY bm25_score DESC
                LIMIT $3
                """,
                tsq, namespace, limit, tenant_id, embedding_model, embedding_dim,
            )

        results: list[Hit] = []
        for r in rows:
            meta = _parse_metadata(r["metadata"])
            results.append({
                "id": r["id"],
                "document_id": r["document_id"],
                "content": r["content"],
                "metadata": meta,
                "bm25_score": r["bm25_score"],  # Public compatibility key for ts_rank.
                "source_filename": meta.get("source_filename"),
            })
        return results

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
        """
        Vector similarity search with a score floor.

        Why the nested SQL query (SELECT * FROM (SELECT ...))?
        Postgres processes the WHERE clause before it processes the SELECT clause.
        If we calculate the vector_score inside the SELECT, Postgres doesn't know what
        "vector_score" is when it hits the WHERE clause, unless we type the whole math formula again!

        To avoid making the database do the math twice, we use a subquery:
        1. The inner query does the math once and labels it 'vector_score'.
        2. The outer query can now safely filter using WHERE vector_score > min_score.

        Only rows embedded with `embedding_model` at `embedding_dim` take part: vectors of another model are
        never compared (Sprint 006). They are counted by `count_stale_vectors`.
        """
        async with tenant_connection(self._pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM (
                    SELECT id, document_id, content, metadata,
                           1.0 - (embedding <=> $1::vector) AS vector_score
                    FROM documents
                    WHERE tenant_id = $5 AND namespace = $2
                      AND embedding_model = $6 AND embedding_dim = $7
                ) scored
                WHERE vector_score > $4
                ORDER BY vector_score DESC
                LIMIT $3
                """,
                embedding, namespace, limit, min_score, tenant_id, embedding_model, embedding_dim,
            )

        results: list[Hit] = []
        for r in rows:
            meta = _parse_metadata(r["metadata"])
            results.append({
                "id": r["id"],
                "document_id": r["document_id"],
                "content": r["content"],
                "metadata": meta,
                "vector_score": r["vector_score"],
                "source_filename": meta.get("source_filename"),
            })
        return results

    async def insert_chunks(
        self,
        tenant_id: UUID,
        document_id: str,
        namespace: str,
        chunks: Sequence[ChunkRow],
        *,
        embedding_model: str,
        embedding_dim: int,
    ) -> None:
        """Insert a batch of chunks.

        Uses a pipelined `executemany` INSERT, not COPY: Postgres refuses COPY FROM into a table with
        row-level security enabled. The metadata dict is serialised to a JSON string first.
        """
        records = [
            (tenant_id, document_id, namespace, chunk.content, chunk.embedding, json.dumps(chunk.metadata),
             embedding_model, embedding_dim)
            for chunk in chunks
        ]
        async with tenant_connection(self._pool, tenant_id) as conn:
            await conn.executemany(
                "INSERT INTO documents "
                "(tenant_id, document_id, namespace, content, embedding, metadata, embedding_model, embedding_dim) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)",
                records,
            )

    async def delete_document(self, tenant_id: UUID, document_id: str, namespace: str) -> int:
        """Delete all chunks for a document_id + namespace. Returns the count of deleted rows."""
        async with tenant_connection(self._pool, tenant_id) as conn:
            result = await conn.execute(
                """
                DELETE FROM documents
                WHERE document_id = $1 AND namespace = $2 AND tenant_id = $3
                """,
                document_id, namespace, tenant_id,
            )
        # asyncpg returns "DELETE N" where N is the row count
        count = int(result.split()[-1])
        logger.info(f"[lifecycle] Deleted {count} chunks for {document_id} in {namespace}")
        return count

    async def document_status(self, tenant_id: UUID, document_id: str, namespace: str, content_hash: str) -> str:
        """`new`, `unchanged` or `updated`, from the registry (primary key tenant_id, namespace, document_id)."""
        async with tenant_connection(self._pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT content_hash FROM document_registry
                WHERE document_id = $1 AND namespace = $2 AND tenant_id = $3
                """,
                document_id, namespace, tenant_id,
            )

        if row is None:
            return "new"
        elif row["content_hash"] == content_hash:
            return "unchanged"
        else:
            return "updated"

    async def register_document(
        self,
        tenant_id: UUID,
        document_id: str,
        namespace: str,
        content_hash: str,
        chunk_count: int,
        source_filename: str,
    ) -> None:
        """Insert or update the registry entry. ON CONFLICT DO UPDATE is one atomic upsert."""
        async with tenant_connection(self._pool, tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO document_registry
                    (tenant_id, document_id, namespace, content_hash, chunk_count, source_filename, last_ingested_at)
                VALUES ($6, $1, $2, $3, $4, $5, NOW())
                ON CONFLICT (tenant_id, namespace, document_id) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    chunk_count = EXCLUDED.chunk_count,
                    source_filename = EXCLUDED.source_filename,
                    last_ingested_at = NOW()
                """,
                document_id, namespace, content_hash, chunk_count, source_filename, tenant_id,
            )

    async def list_documents(
        self, tenant_id: UUID, namespace: str | None, visible_kbs: Sequence[str] | None
    ) -> list[DocumentRecord]:
        # Row-level security limits the query to the caller's tenant; the explicit filter keeps the index in use.
        async with tenant_connection(self._pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT document_id, namespace, source_filename,
                       content_hash, chunk_count, last_ingested_at
                FROM document_registry
                WHERE tenant_id = $1 AND ($2::text IS NULL OR namespace = $2)
                  AND ($3::text[] IS NULL OR namespace = ANY($3))
                ORDER BY last_ingested_at DESC
                """,
                tenant_id, namespace or None, list(visible_kbs) if visible_kbs is not None else None,
            )
        return [
            DocumentRecord(
                document_id=r["document_id"], namespace=r["namespace"], source_filename=r["source_filename"],
                content_hash=r["content_hash"], chunk_count=r["chunk_count"], last_ingested_at=r["last_ingested_at"],
            )
            for r in rows
        ]

    async def count_stale_vectors(self, embedding_model: str, embedding_dim: int) -> int:
        """Chunks of every tenant embedded with another model or dimension. A count only: the SECURITY DEFINER
        function `count_stale_vectors` (migration 0007) reads across tenants and returns no row content."""
        count = await self._pool.fetchval("SELECT count_stale_vectors($1, $2)", embedding_model, embedding_dim)
        return int(count or 0)

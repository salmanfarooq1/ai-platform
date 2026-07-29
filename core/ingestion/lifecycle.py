"""
core/ingestion/lifecycle.py

Document lifecycle management for the RAG platform.

Provides three operations:
  1. compute_content_hash(content_bytes) → SHA-256 hex string
  2. check_document_status(pool, document_id, namespace, new_hash) → "new" | "unchanged" | "updated"
  3. delete_document_chunks(pool, document_id, namespace) → count of deleted rows
  4. register_document(pool, document_id, namespace, content_hash, chunk_count, source_filename) → None

These are called by the /ingest route handler before and after the chunking pipeline.
"""
import hashlib
from asyncpg import Pool
import logging

logger = logging.getLogger("core.lifecycle")


def compute_content_hash(content: bytes) -> str:
    """
    SHA-256 hash of raw file bytes.

    Returns a 64-character lowercase hex string.
    Deterministic: same bytes always produce the same hash.

    Why SHA-256 and not MD5:
    MD5 is faster (~2x) but has known collision attacks.
    For a compliance platform where document integrity matters,
    SHA-256 is the correct choice. The speed difference on files
    under 100MB is negligible (milliseconds).
    """
    return hashlib.sha256(content).hexdigest()


async def check_document_status(
    pool: Pool,
    document_id: str,
    namespace: str,
    new_hash: str,
) -> str:
    """
    Compare the new content hash against the stored one.

    Returns:
      "new"       — document has never been ingested in this namespace
      "unchanged" — content hash matches, no re-ingestion needed
      "updated"   — content hash differs, old chunks should be deleted

    This query hits the document_registry table, which has a PRIMARY KEY
    on (document_id, namespace). The lookup is an index scan, not a
    sequential scan. It returns in microseconds.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT content_hash FROM document_registry
            WHERE document_id = $1 AND namespace = $2
            """,
            document_id, namespace,
        )

    if row is None:
        return "new"
    elif row["content_hash"] == new_hash:
        return "unchanged"
    else:
        return "updated"


async def delete_document_chunks(
    pool: Pool,
    document_id: str,
    namespace: str,
) -> int:
    """
    Delete all chunks for a document_id + namespace from the documents table.

    Returns the count of deleted rows so the API can report it.

    This uses DELETE with RETURNING to get the count in a single query
    instead of a separate COUNT query followed by a DELETE.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM documents
            WHERE document_id = $1 AND namespace = $2
            """,
            document_id, namespace,
        )
    # asyncpg returns "DELETE N" where N is the row count
    count = int(result.split()[-1])
    logger.info(f"[lifecycle] Deleted {count} chunks for {document_id} in {namespace}")
    return count


async def register_document(
    pool: Pool,
    document_id: str,
    namespace: str,
    content_hash: str,
    chunk_count: int,
    source_filename: str,
) -> None:
    """
    Insert or update the document registry entry.

    Uses INSERT ... ON CONFLICT DO UPDATE (upsert pattern).
    On first ingest: creates the row.
    On re-ingest with changed content: updates hash, chunk_count, timestamp.
    On re-ingest with same content: this function is never called (the route
    short-circuits on "unchanged" status).

    ON CONFLICT DO UPDATE is PostgreSQL's built-in upsert. It is a single
    atomic operation, not a SELECT-then-INSERT/UPDATE sequence. No race
    condition between two concurrent ingests of the same document.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO document_registry
                (document_id, namespace, content_hash, chunk_count, source_filename, last_ingested_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (document_id, namespace) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                chunk_count = EXCLUDED.chunk_count,
                source_filename = EXCLUDED.source_filename,
                last_ingested_at = NOW()
            """,
            document_id, namespace, content_hash, chunk_count, source_filename,
        )
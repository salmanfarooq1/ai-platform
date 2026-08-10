"""
api/routers/docs.py

Document registry listing endpoint.
Powers the frontend Documents management page.

Reads from document_registry, which is written by
core/ingestion/lifecycle.py::register_document() on every
successful /ingest call.

Column names confirmed against core/database/schema.sql and
core/ingestion/lifecycle.py — the timestamp column is
`last_ingested_at`, NOT `ingested_at`.
"""
from asyncpg import Pool
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(tags=["documents"])


async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool


@router.get("/documents")
async def list_documents(
    namespace: str | None = Query(default=None, description="Filter by namespace. Omit to list all."),
    pool: Pool = Depends(get_db_pool),
):
    """List all ingested documents from the document registry.

    Returns document metadata including content hash (for deduplication
    visibility), chunk count, source filename, and last ingested timestamp.
    Filter by namespace to show only documents in a specific scope.
    """
    if namespace:
        rows = await pool.fetch(
            """
            SELECT document_id, namespace, source_filename,
                   content_hash, chunk_count, last_ingested_at
            FROM document_registry
            WHERE namespace = $1
            ORDER BY last_ingested_at DESC
            """,
            namespace,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT document_id, namespace, source_filename,
                   content_hash, chunk_count, last_ingested_at
            FROM document_registry
            ORDER BY last_ingested_at DESC
            """
        )

    return {
        "documents": [
            {
                "document_id": r["document_id"],
                "namespace": r["namespace"],
                "source_filename": r["source_filename"],
                "content_hash": r["content_hash"],
                "chunk_count": r["chunk_count"],
                "last_ingested_at": r["last_ingested_at"].isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }

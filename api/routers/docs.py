"""
api/routers/docs.py

Document registry listing endpoint.
Powers the frontend Documents management page.

Reads from document_registry, which is written by
core/ingestion/lifecycle.py::register_document() on every
successful /ingest call.

Column names confirmed against migrations/versions/0001_baseline.py and
core/ingestion/lifecycle.py — the timestamp column is
`last_ingested_at`, NOT `ingested_at`.
"""
from asyncpg import Pool
from fastapi import APIRouter, Depends, Query, Request

from api.auth import require_kb, require_scope
from api.gateway_deps import entry_action, gateway_context
from core.database.tenant import tenant_connection
from core.identity.models import Principal, Scope
from gateway import ActionKind, EnforcementContext, require

router = APIRouter(tags=["documents"])


async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool


@router.get("/documents")
async def list_documents(
    request: Request,
    namespace: str | None = Query(default=None, description="Filter by namespace. Omit to list all."),
    pool: Pool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.KB_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
):
    """List all ingested documents from the document registry.

    Returns document metadata including content hash (for deduplication
    visibility), chunk count, source filename, and last ingested timestamp.
    Filter by namespace to show only documents in a specific scope.
    """
    await require(ctx, entry_action(request.url.path, ActionKind.KB_READ, namespace or None))
    if namespace:
        await require_kb(pool, principal, namespace)
    tenant_id = principal.tenant_id
    # Row-level security limits the query to the caller's tenant; the explicit filter keeps the index in use.
    async with tenant_connection(pool, tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT document_id, namespace, source_filename,
                   content_hash, chunk_count, last_ingested_at
            FROM document_registry
            WHERE tenant_id = $1 AND ($2::text IS NULL OR namespace = $2)
              AND ($3::text[] IS NULL OR namespace = ANY($3))
            ORDER BY last_ingested_at DESC
            """,
            tenant_id, namespace or None, ctx.boundary.visible_kbs(),
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

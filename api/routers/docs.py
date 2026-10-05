"""
api/routers/docs.py

Document registry listing endpoint.
Powers the frontend Documents management page.

Reads from document_registry, which is written by
`KnowledgeStore.register_document()` (adapters/pg_knowledge.py) on every
successful /ingest call.

Column names confirmed against migrations/versions/0001_baseline.py and
adapters/pg_knowledge.py — the timestamp column is
`last_ingested_at`, NOT `ingested_at`.
"""
from fastapi import APIRouter, Depends, Query, Request

from api.auth import require_kb, require_scope
from api.dependencies import adapters_of
from api.gateway_deps import entry_action, gateway_context
from core.identity.models import Principal, Scope
from gateway import ActionKind, EnforcementContext, require

router = APIRouter(tags=["documents"])


@router.get("/documents")
async def list_documents(
    request: Request,
    namespace: str | None = Query(default=None, description="Filter by namespace. Omit to list all."),
    principal: Principal = Depends(require_scope(Scope.KB_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
):
    """List all ingested documents from the document registry.

    Returns document metadata including content hash (for deduplication
    visibility), chunk count, source filename, and last ingested timestamp.
    Filter by namespace to show only documents in a specific scope.
    """
    store = adapters_of(request).knowledge
    await require(ctx, entry_action(request.url.path, ActionKind.KB_READ, namespace or None))
    if namespace:
        await require_kb(store, principal, namespace)
    rows = await store.list_documents(principal.tenant_id, namespace or None, ctx.boundary.visible_kbs())

    return {
        "documents": [
            {
                "document_id": r.document_id,
                "namespace": r.namespace,
                "source_filename": r.source_filename,
                "content_hash": r.content_hash,
                "chunk_count": r.chunk_count,
                "last_ingested_at": r.last_ingested_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }

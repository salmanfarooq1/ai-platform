import logging
import os
import tempfile

from asyncpg import Pool
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from api.auth import require_kb, require_scope
from api.gateway_deps import entry_action, gateway_context
from api.models.schemas import IngestResponse
from config import LLM_CONFIG
from core.identity.models import Principal, Scope
from core.ingestion.lifecycle import (
    check_document_status,
    compute_content_hash,
    delete_document_chunks,
    register_document,
)
from core.pipeline.db_ingest import ingestion_pipeline
from gateway import Action, ActionKind, EnforcementContext, require
from gateway.estimate import estimate_tokens

logger = logging.getLogger("api.ingest")
router = APIRouter()

# Dependency — pulls the shared pool from app.state.
# Every route that needs DB access declares this as a dependency.
# FastAPI calls it automatically and injects the result.
# This is why we don't import app directly inside route handlers —
# tight coupling to the app object makes testing hard.
async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: Request,
    file: UploadFile = File(...),
    namespace: str = "default",
    document_id: str | None = None,
    pool: Pool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.KB_WRITE)),
    ctx: EnforcementContext = Depends(gateway_context),
):
    tenant_id = principal.tenant_id
    await require(ctx, entry_action(request.url.path, ActionKind.KB_WRITE, namespace))
    # Ingest embeds the file's chunks: the embedding model must be allowed too.
    await require(ctx, Action(ActionKind.MODEL_INVOKE, LLM_CONFIG["embedding_model"], estimated_tokens=estimate_tokens("")))
    await require_kb(pool, principal, namespace)
    filename = file.filename or ""
    doc_id = document_id or filename
    # Set minimal usage so FinOpsMiddleware stamps X-Query-ID on the response.
    # Ingest has no LLM cost, but X-Query-ID lets the frontend tie each ingest
    # result to a specific server-side request for debugging and MetaBar display.
    request.state.usage = {"namespace": namespace}
    content = await file.read()
    content_hash = compute_content_hash(content)

    # Check document lifecycle status
    status = await check_document_status(pool, doc_id, namespace, content_hash, tenant_id=tenant_id)

    # Case 1: Unchanged file — short-circuit and skip processing
    if status == "unchanged":
        return IngestResponse(
            document_id=doc_id,
            namespace=namespace,
            total_chunks=0,
            total_time_seconds=0.0,
            throughput_chunks_per_second=0.0,
            status="unchanged",
            content_hash=content_hash,
            chunks_deleted=0,
        )

    # Case 2: Updated file — delete old chunks before re-ingesting
    chunks_deleted = 0
    if status == "updated":
        chunks_deleted = await delete_document_chunks(pool, doc_id, namespace, tenant_id=tenant_id)

    # Case 3 & 2 (New or Updated): Run chunking & embedding pipeline
    tmp_path = None
    try:
        suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        metrics = await ingestion_pipeline(
            input_file_path=tmp_path,
            document_id=doc_id,
            namespace=namespace,
            pool=pool,
            source_filename=filename or None,
            tenant_id=tenant_id,
        )

        # Register document in document_registry
        await register_document(
            pool=pool,
            document_id=doc_id,
            namespace=namespace,
            content_hash=content_hash,
            chunk_count=metrics.get("total_chunks", 0),
            source_filename=filename,
            tenant_id=tenant_id,
        )

    except ValueError:
        # The detail goes to the log only: it can carry file paths or parser internals.
        logger.warning("ingest rejected %r for tenant %s", filename, tenant_id, exc_info=True)
        raise HTTPException(status_code=415, detail="Unsupported or unreadable file")
    except Exception:
        logger.error("ingest failed for %r, tenant %s", filename, tenant_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Ingestion failed")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return IngestResponse(
        document_id=doc_id,
        namespace=namespace,
        status=status,
        content_hash=content_hash,
        chunks_deleted=chunks_deleted,
        **metrics,
    )

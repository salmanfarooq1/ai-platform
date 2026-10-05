import logging
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from api.auth import require_kb, require_scope
from api.dependencies import adapters_of
from api.gateway_deps import entry_action, gateway_context
from api.models.schemas import IngestResponse
from config import LLM_CONFIG
from core.identity.models import Principal, Scope
from core.ingestion.lifecycle import compute_content_hash
from core.pipeline.db_ingest import ingestion_pipeline
from gateway import Action, ActionKind, EnforcementContext, require
from gateway.estimate import estimate_tokens

logger = logging.getLogger("api.ingest")
router = APIRouter()

@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: Request,
    file: UploadFile = File(...),
    namespace: str = "default",
    document_id: str | None = None,
    principal: Principal = Depends(require_scope(Scope.KB_WRITE)),
    ctx: EnforcementContext = Depends(gateway_context),
):
    tenant_id = principal.tenant_id
    adapters = adapters_of(request)
    await require(ctx, entry_action(request.url.path, ActionKind.KB_WRITE, namespace))
    # Ingest embeds the file's chunks: the embedding model must be allowed too.
    await require(ctx, Action(ActionKind.MODEL_INVOKE, LLM_CONFIG["embedding_model"], estimated_tokens=estimate_tokens("")))
    await require_kb(adapters.knowledge, principal, namespace)
    filename = file.filename or ""
    doc_id = document_id or filename
    # Set minimal usage so FinOpsMiddleware stamps X-Query-ID on the response.
    # Ingest has no LLM cost, but X-Query-ID lets the frontend tie each ingest
    # result to a specific server-side request for debugging and MetaBar display.
    request.state.usage = {"namespace": namespace}
    content = await file.read()
    content_hash = compute_content_hash(content)

    # Check document lifecycle status
    status = await adapters.knowledge.document_status(tenant_id, doc_id, namespace, content_hash)

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
        chunks_deleted = await adapters.knowledge.delete_document(tenant_id, doc_id, namespace)

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
            source_filename=filename or None,
            store=adapters.knowledge,
            embeddings=adapters.embeddings,
            tenant_id=tenant_id,
        )

        # Register document in document_registry
        await adapters.knowledge.register_document(
            tenant_id, doc_id, namespace, content_hash, metrics.get("total_chunks", 0), filename,
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

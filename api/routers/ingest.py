import os
import tempfile

from asyncpg import Pool
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from api.models.schemas import IngestResponse
from core.ingestion.lifecycle import (
    check_document_status,
    compute_content_hash,
    delete_document_chunks,
    register_document,
)
from core.pipeline.db_ingest import ingestion_pipeline

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
    document_id: str = None,
    pool: Pool = Depends(get_db_pool),
):
    doc_id = document_id or file.filename
    content = await file.read()
    content_hash = compute_content_hash(content)

    # Check document lifecycle status
    status = await check_document_status(pool, doc_id, namespace, content_hash)

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
        chunks_deleted = await delete_document_chunks(pool, doc_id, namespace)

    # Case 3 & 2 (New or Updated): Run chunking & embedding pipeline
    tmp_path = None
    try:
        suffix = "." + file.filename.rsplit(".", 1)[-1] if "." in file.filename else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        metrics = await ingestion_pipeline(
            input_file_path=tmp_path,
            document_id=doc_id,
            namespace=namespace,
            pool=pool,
        )

        # Register document in document_registry
        await register_document(
            pool=pool,
            document_id=doc_id,
            namespace=namespace,
            content_hash=content_hash,
            chunk_count=metrics.get("total_chunks", 0),
            source_filename=file.filename,
        )

    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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

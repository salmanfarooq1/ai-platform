import tempfile
import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Request
from asyncpg import Pool
from api.models.schemas import IngestRequest, IngestResponse
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
    pool: Pool = Depends(get_db_pool),   # injected automatically
):
    # Default document_id to filename if not provided
    doc_id = document_id or file.filename

    # Pipeline expects a file path, not bytes.
    # Write upload to a temp file, run pipeline, clean up.
    # NamedTemporaryFile with delete=False so we control deletion timing.
    try:
        suffix = "." + file.filename.rsplit(".", 1)[-1] if "." in file.filename else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        
        metrics = await ingestion_pipeline(
            input_file_path=tmp_path,
            document_id=doc_id,
            namespace=namespace,
            pool = pool
        )
    except ValueError as e:
        # get_chunker raises ValueError for unsupported file types
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Always clean up temp file — even if pipeline raised
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return IngestResponse(
        document_id=doc_id,
        namespace=namespace,
        **metrics
    )
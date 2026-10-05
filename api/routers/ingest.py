import logging
import re

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile

from api.auth import require_kb, require_scope
from api.dependencies import adapters_of
from api.gateway_deps import entry_action, gateway_context
from api.models.jobs import JobAccepted
from config import LLM_CONFIG
from core.database import jobs
from core.database.tenant import tenant_connection
from core.identity.models import Principal, Scope
from core.ingestion.lifecycle import compute_content_hash
from core.settings import get_settings
from gateway import Action, ActionKind, EnforcementContext, require
from gateway.estimate import estimate_tokens

logger = logging.getLogger("api.ingest")
router = APIRouter()

_KEY = re.compile(r"^[\x21-\x7e]{1,200}$")  # printable ASCII, no spaces, at most 200 characters


@router.post(
    "/ingest",
    response_model=JobAccepted,
    status_code=202,
    responses={200: {"model": JobAccepted, "description": "The Idempotency-Key already named a job: it is returned"}},
)
async def ingest(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    namespace: str = "default",
    document_id: str | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_scope(Scope.KB_WRITE)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> JobAccepted:
    """Accept a file for ingestion and return at once with the job that will ingest it (`GET /v1/jobs/{id}`).

    The raw bytes are stored under their SHA-256 before anything is parsed. The same `Idempotency-Key` (per tenant)
    returns the same job with 200 instead of creating a second one.
    """
    tenant_id = principal.tenant_id
    adapters = adapters_of(request)
    await require(ctx, entry_action(request.url.path, ActionKind.KB_WRITE, namespace))
    # Ingest embeds the file's chunks: the embedding model must be allowed too.
    await require(ctx, Action(ActionKind.MODEL_INVOKE, LLM_CONFIG["embedding_model"], estimated_tokens=estimate_tokens("")))
    await require_kb(adapters.knowledge, principal, namespace)
    if idempotency_key is not None and not _KEY.match(idempotency_key):
        raise HTTPException(status_code=400, detail={"error": "invalid_idempotency_key", "reason": "The Idempotency-Key must be 1 to 200 printable characters"})
    # Set minimal usage so FinOpsMiddleware stamps X-Query-ID on the response.
    request.state.usage = {"namespace": namespace}
    pool = request.app.state.db_pool

    if idempotency_key is not None:  # a repeat: answer before the file is read or stored again
        async with tenant_connection(pool, tenant_id) as conn:
            known = await conn.fetchrow("SELECT id, status FROM jobs WHERE tenant_id = $1 AND idempotency_key = $2", tenant_id, idempotency_key)
        if known is not None:
            response.status_code = 200
            return JobAccepted(job_id=known["id"], status=known["status"])

    filename = file.filename or ""
    doc_id = document_id or filename
    content = await file.read()
    content_hash = compute_content_hash(content)
    object_key = await adapters.objects.put(content)  # the same bytes are stored once
    payload = {
        "namespace": namespace, "document_id": doc_id, "filename": filename, "content_hash": content_hash,
        "object_key": object_key,
    }
    try:
        async with tenant_connection(pool, tenant_id) as conn:
            job, created = await jobs.enqueue(
                conn, tenant_id, jobs.KIND_INGEST, payload, idempotency_key=idempotency_key,
                max_attempts=get_settings().job_max_attempts, resource=f"{namespace}/{doc_id}",
                principal_id=principal.id, namespace=namespace,
            )
    except jobs.PayloadTooLarge:
        raise HTTPException(status_code=413, detail="The document id or file name is too long") from None
    if not created:
        response.status_code = 200
    return JobAccepted(job_id=job.id, status=job.status)  # type: ignore[arg-type]

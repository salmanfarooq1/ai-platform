"""The `ingest` job: read the stored raw file, chunk, embed and store it, then register the document.

The route already stored the bytes in the object store under their SHA-256 and put the key in the payload, so a
retry or a second worker reads the same bytes. The handler can run again without harm: it replaces the document's
chunks before it writes them, so a half-finished earlier attempt leaves nothing behind. When it finishes it
returns the `platform.ingest.completed.v1` event; the worker writes it to the outbox in the transaction that
marks the job succeeded.
"""
import logging
import os
import tempfile
from typing import Any

from api.services.model_calls import build_model_caller
from core.database.jobs import JobRow
from core.identity.models import Principal, parse_scopes
from core.pipeline.db_ingest import ingestion_pipeline
from core.settings import Settings
from gateway import GatewayDenied, GatewayRuntime
from gateway.context import build_context
from ports import INGEST_COMPLETED, Adapters, CloudEvent, ObjectNotFound
from workers.types import Handler, JobContext, JobOutput, PermanentJobError

logger = logging.getLogger("workers.ingest")

EVENT_SOURCE = "/ingest"


def completed_event(job: JobRow, status: str, total_chunks: int) -> CloudEvent:
    """No file content and no text: ids, the hash and counts."""
    p = job.payload
    return CloudEvent(
        type=INGEST_COMPLETED, source=EVENT_SOURCE, subject=str(job.id), tenantid=str(job.tenant_id),
        data={
            "job_id": str(job.id), "document_id": p["document_id"], "namespace": p["namespace"],
            "content_hash": p["content_hash"], "status": status, "total_chunks": total_chunks,
        },
    )


def make_ingest_handler(adapters: Adapters, gateway_runtime: GatewayRuntime, settings: Settings) -> Handler:
    knowledge, objects = adapters.knowledge, adapters.objects

    async def handle(job: JobRow, ctx: JobContext) -> JobOutput:
        p: dict[str, Any] = job.payload
        tenant_id, doc_id, namespace = job.tenant_id, p["document_id"], p["namespace"]
        filename, content_hash = p.get("filename") or "", p["content_hash"]
        try:
            content = await objects.get(p["object_key"])
        except ObjectNotFound:
            raise PermanentJobError("object_missing", "the stored file is gone") from None

        if job.principal_id is None:
            raise PermanentJobError("principal_missing", "ingest job has no persisted principal")
        identity = await ctx.pool.fetchrow("SELECT * FROM auth_lookup_preview($1)", job.principal_id)
        if (identity is None or identity["tenant_id"] != tenant_id or identity["principal_disabled_at"] is not None):
            raise PermanentJobError("principal_unavailable", "ingest job principal is unavailable")
        principal = Principal(
            id=identity["principal_id"], tenant_id=identity["tenant_id"], kind=identity["principal_kind"],
            scopes=parse_scopes(identity["scopes"]),
        )
        request_id = p.get("request_id") or str(job.id)
        enforcement = await build_context(gateway_runtime, principal, request_id, job.id.hex)
        caller = build_model_caller(adapters, settings, adapters.embeddings)

        status = await knowledge.document_status(tenant_id, doc_id, namespace, content_hash)
        if status == "unchanged":  # the same bytes are already ingested: nothing to do
            await ctx.progress(0, 0)
            return JobOutput(result={"status": status, "total_chunks": 0}, events=[completed_event(job, status, 0)])

        # New or updated. Always clear the document first: a crashed earlier attempt may have left chunks behind.
        deleted = await knowledge.delete_document(tenant_id, doc_id, namespace)
        tmp_path = None
        try:
            suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".txt"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            async def embed_batch(chunks):
                result = await caller.embed(
                    enforcement, str(settings.embed_model), [chunk.content for chunk in chunks],
                )
                for chunk, vector in zip(chunks, result.vectors):
                    chunk.embedding = vector
                return chunks, result.model, result.dim

            metrics = await ingestion_pipeline(
                input_file_path=tmp_path, document_id=doc_id, namespace=namespace, source_filename=filename or None,
                store=knowledge, embeddings=adapters.embeddings, tenant_id=tenant_id, on_progress=ctx.progress,
                embed_batch=embed_batch,
            )
            await knowledge.register_document(
                tenant_id, doc_id, namespace, content_hash, metrics.get("total_chunks", 0), filename,
            )
        except ValueError:
            # The detail goes to the log only: it can carry file paths or parser internals.
            logger.warning("ingest rejected %r for tenant %s", filename, tenant_id, exc_info=True)
            raise PermanentJobError("unsupported_file") from None
        except GatewayDenied as exc:
            # Earlier batches may have inserted rows; a denied attempt never leaves a partial document.
            await knowledge.delete_document(tenant_id, doc_id, namespace)
            raise PermanentJobError(
                "model_not_allowed", f"embedding model invocation was denied (reason: {exc.decision.reason})",
            ) from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        total = int(metrics.get("total_chunks", 0))
        return JobOutput(
            result={"status": status, "total_chunks": total, "chunks_deleted": deleted},
            events=[completed_event(job, status, total)],
        )

    return handle

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

from core.database.jobs import JobRow
from core.pipeline.db_ingest import ingestion_pipeline
from ports import INGEST_COMPLETED, CloudEvent, EmbeddingPort, KnowledgeStore, ObjectNotFound, ObjectStore
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


def make_ingest_handler(knowledge: KnowledgeStore, embeddings: EmbeddingPort, objects: ObjectStore) -> Handler:
    async def handle(job: JobRow, ctx: JobContext) -> JobOutput:
        p: dict[str, Any] = job.payload
        tenant_id, doc_id, namespace = job.tenant_id, p["document_id"], p["namespace"]
        filename, content_hash = p.get("filename") or "", p["content_hash"]
        try:
            content = await objects.get(p["object_key"])
        except ObjectNotFound:
            raise PermanentJobError("object_missing", "the stored file is gone") from None

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
            metrics = await ingestion_pipeline(
                input_file_path=tmp_path, document_id=doc_id, namespace=namespace, source_filename=filename or None,
                store=knowledge, embeddings=embeddings, tenant_id=tenant_id, on_progress=ctx.progress,
            )
            await knowledge.register_document(
                tenant_id, doc_id, namespace, content_hash, metrics.get("total_chunks", 0), filename,
            )
        except ValueError:
            # The detail goes to the log only: it can carry file paths or parser internals.
            logger.warning("ingest rejected %r for tenant %s", filename, tenant_id, exc_info=True)
            raise PermanentJobError("unsupported_file") from None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        total = int(metrics.get("total_chunks", 0))
        return JobOutput(
            result={"status": status, "total_chunks": total, "chunks_deleted": deleted},
            events=[completed_event(job, status, total)],
        )

    return handle

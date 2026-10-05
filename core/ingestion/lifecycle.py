"""
core/ingestion/lifecycle.py

Document lifecycle helpers for the RAG platform. The registry SQL (status check, delete, register) moved to
`adapters/pg_knowledge.py` behind the `KnowledgeStore` port (Sprint 006); what stays here is pure.

  compute_content_hash(content_bytes) → SHA-256 hex string

The /ingest route handler calls it, then `store.document_status(...)`, the pipeline, and `store.register_document(...)`.
"""
import hashlib


def compute_content_hash(content: bytes) -> str:
    """
    SHA-256 hash of raw file bytes.

    Returns a 64-character lowercase hex string.
    Deterministic: same bytes always produce the same hash.

    Why SHA-256 and not MD5:
    MD5 is faster (~2x) but has known collision attacks.
    For a compliance platform where document integrity matters,
    SHA-256 is the correct choice. The speed difference on files
    under 100MB is negligible (milliseconds).
    """
    return hashlib.sha256(content).hexdigest()

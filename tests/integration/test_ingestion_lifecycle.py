"""Ingestion lifecycle against real Postgres: new, unchanged and updated documents."""
from pathlib import Path
from uuid import UUID

from core.ingestion.lifecycle import compute_content_hash
from core.pipeline.db_ingest import ingestion_pipeline

V1 = b"# GDPR\n\nBreach notification must happen within 72 hours.\n"
V2 = b"# GDPR\n\nBreach notification must happen within 48 hours of discovery.\n"


async def _ingest(store, embeddings, tmp_path: Path, content: bytes, tenant, doc_id="gdpr.md", namespace="legal"):
    """Mirror what the /ingest route does, minus HTTP."""
    tid = UUID(tenant.id)
    content_hash = compute_content_hash(content)
    status = await store.document_status(tid, doc_id, namespace, content_hash)
    if status == "unchanged":
        return status, 0, 0
    deleted = await store.delete_document(tid, doc_id, namespace) if status == "updated" else 0
    path = tmp_path / doc_id
    path.write_bytes(content)
    metrics = await ingestion_pipeline(str(path), doc_id, namespace, store=store, embeddings=embeddings, tenant_id=tid)
    await store.register_document(tid, doc_id, namespace, content_hash, metrics["total_chunks"], doc_id)
    return status, deleted, metrics["total_chunks"]


async def test_new_document_writes_chunks_and_registry(knowledge_store, db_pool, owner_pool, tenant_a, fake_embeddings, tmp_path):
    status, deleted, chunks = await _ingest(knowledge_store, fake_embeddings, tmp_path, V1, tenant_a)

    assert (status, deleted) == ("new", 0)
    assert chunks >= 1
    rows = await owner_pool.fetch("SELECT document_id, namespace, content FROM documents")
    assert len(rows) == chunks
    assert {(r["document_id"], r["namespace"]) for r in rows} == {("gdpr.md", "legal")}
    assert "72 hours" in " ".join(r["content"] for r in rows)
    reg = await owner_pool.fetchrow("SELECT * FROM document_registry")
    assert reg["content_hash"] == compute_content_hash(V1)
    assert reg["chunk_count"] == chunks
    assert reg["source_filename"] == "gdpr.md"
    # embeddings really went through the fake: one call for the single batch
    assert len(fake_embeddings.calls) == 1


async def test_unchanged_document_is_skipped(knowledge_store, db_pool, owner_pool, tenant_a, fake_embeddings, tmp_path):
    await _ingest(knowledge_store, fake_embeddings, tmp_path, V1, tenant_a)
    count_before = await owner_pool.fetchval("SELECT count(*) FROM documents")
    calls_before = len(fake_embeddings.calls)

    status, deleted, chunks = await _ingest(knowledge_store, fake_embeddings, tmp_path, V1, tenant_a)

    assert (status, deleted, chunks) == ("unchanged", 0, 0)
    assert await owner_pool.fetchval("SELECT count(*) FROM documents") == count_before
    assert len(fake_embeddings.calls) == calls_before  # nothing was embedded


async def test_updated_document_replaces_old_chunks(knowledge_store, db_pool, owner_pool, tenant_a, fake_embeddings, tmp_path):
    _, _, first_chunks = await _ingest(knowledge_store, fake_embeddings, tmp_path, V1, tenant_a)

    status, deleted, second_chunks = await _ingest(knowledge_store, fake_embeddings, tmp_path, V2, tenant_a)

    assert status == "updated"
    assert deleted == first_chunks
    contents = " ".join(r["content"] for r in await owner_pool.fetch("SELECT content FROM documents"))
    assert "48 hours" in contents
    assert "72 hours" not in contents
    reg = await owner_pool.fetchrow("SELECT content_hash, chunk_count FROM document_registry")
    assert reg["content_hash"] == compute_content_hash(V2)
    assert reg["chunk_count"] == second_chunks
    assert await owner_pool.fetchval("SELECT count(*) FROM document_registry") == 1


async def test_same_document_id_in_two_namespaces_is_independent(knowledge_store, db_pool, owner_pool, tenant_a, fake_embeddings, tmp_path):
    await _ingest(knowledge_store, fake_embeddings, tmp_path, V1, tenant_a, namespace="legal")
    status, _, _ = await _ingest(knowledge_store, fake_embeddings, tmp_path, V1, tenant_a, namespace="kyc_aml")

    assert status == "new"
    assert await owner_pool.fetchval("SELECT count(*) FROM document_registry") == 2
    deleted = await knowledge_store.delete_document(UUID(tenant_a.id), "gdpr.md", "legal")
    assert deleted >= 1
    remaining = await owner_pool.fetch("SELECT DISTINCT namespace FROM documents")
    assert [r["namespace"] for r in remaining] == ["kyc_aml"]


async def test_fts_vector_is_filled_by_the_trigger(knowledge_store, db_pool, owner_pool, tenant_a, fake_embeddings, tmp_path):
    await _ingest(knowledge_store, fake_embeddings, tmp_path, V1, tenant_a)
    matches = await owner_pool.fetchval(
        "SELECT count(*) FROM documents WHERE fts_vector @@ plainto_tsquery('english', 'breach notification')"
    )
    assert matches >= 1


async def test_chunks_store_the_real_upload_filename_not_the_temp_path(knowledge_store, db_pool, owner_pool, tenant_a, fake_embeddings, tmp_path):
    """Regression B3: metadata used to hold only the temp file name, so citations said 'unknown'."""
    import json

    from api.services.retriever import RetrieverConfig, retrieve

    path = tmp_path / "tmpab12cd.md"
    path.write_bytes(V1)
    await ingestion_pipeline(str(path), "gdpr.md", "legal", source_filename="gdpr.md", store=knowledge_store, embeddings=fake_embeddings, tenant_id=UUID(tenant_a.id))

    metas = [json.loads(r["metadata"]) for r in await owner_pool.fetch("SELECT metadata FROM documents")]
    assert {m["source_filename"] for m in metas} == {"gdpr.md"}
    q = "breach notification"
    found = await retrieve(knowledge_store, q, await fake_embeddings.embed([q]), "legal", RetrieverConfig(top_k=1), tenant_id=UUID(tenant_a.id))
    assert found[0]["source_filename"] == "gdpr.md"


async def test_source_filename_defaults_to_the_file_name(knowledge_store, db_pool, owner_pool, tenant_a, fake_embeddings, tmp_path):
    import json

    path = tmp_path / "local.md"
    path.write_bytes(V1)
    await ingestion_pipeline(str(path), "x", "legal", store=knowledge_store, embeddings=fake_embeddings, tenant_id=UUID(tenant_a.id))
    metas = [json.loads(r["metadata"]) for r in await owner_pool.fetch("SELECT metadata FROM documents")]
    assert {m["source_filename"] for m in metas} == {"local.md"}

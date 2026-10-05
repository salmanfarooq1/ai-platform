"""Hybrid retrieval against real Postgres (pgvector + full-text) with fake embeddings."""
from uuid import UUID

from api.services.retriever import RetrieverConfig, retrieve
from core.ingestion.lifecycle import compute_content_hash
from core.pipeline.db_ingest import ingestion_pipeline

GDPR = "# GDPR\n\nPersonal data breach notification must reach the supervisory authority within 72 hours.\n"
CCPA = "# CCPA\n\nConsumers may request deletion of personal information held by a business.\n"


async def _ingest_text(store, embeddings, tmp_path, doc_id, text, namespace, tenant):
    path = tmp_path / doc_id
    path.write_text(text)
    await ingestion_pipeline(str(path), doc_id, namespace, store=store, embeddings=embeddings, tenant_id=UUID(tenant.id))
    return compute_content_hash(text.encode())


async def test_hybrid_returns_the_matching_chunk_first(knowledge_store, tenant_a, fake_embeddings, tmp_path):
    await _ingest_text(knowledge_store, fake_embeddings, tmp_path, "gdpr.md", GDPR, "legal", tenant_a)
    await _ingest_text(knowledge_store, fake_embeddings, tmp_path, "ccpa.md", CCPA, "legal", tenant_a)
    query = "breach notification within 72 hours"

    results = await retrieve(knowledge_store, query, await fake_embeddings.embed([query]), "legal", RetrieverConfig(top_k=2, mode="hybrid"), tenant_id=UUID(tenant_a.id))

    assert results[0]["document_id"] == "gdpr.md"
    assert "72 hours" in results[0]["content"]
    assert results[0]["rrf_score"] > 0
    assert {r["document_id"] for r in results} <= {"gdpr.md", "ccpa.md"}


async def test_retrieval_respects_namespace(knowledge_store, tenant_a, fake_embeddings, tmp_path):
    await _ingest_text(knowledge_store, fake_embeddings, tmp_path, "gdpr.md", GDPR, "legal", tenant_a)
    query = "breach notification within 72 hours"

    other = await retrieve(knowledge_store, query, await fake_embeddings.embed([query]), "kyc_aml", RetrieverConfig(top_k=5, mode="hybrid"), tenant_id=UUID(tenant_a.id))
    same = await retrieve(knowledge_store, query, await fake_embeddings.embed([query]), "legal", RetrieverConfig(top_k=5, mode="hybrid"), tenant_id=UUID(tenant_a.id))

    assert other == []
    assert [r["document_id"] for r in same] == ["gdpr.md"]


async def test_vector_only_ranks_by_shared_words(knowledge_store, tenant_a, fake_embeddings, tmp_path):
    await _ingest_text(knowledge_store, fake_embeddings, tmp_path, "gdpr.md", GDPR, "legal", tenant_a)
    await _ingest_text(knowledge_store, fake_embeddings, tmp_path, "ccpa.md", CCPA, "legal", tenant_a)
    query = "consumers deletion of personal information"

    results = await retrieve(knowledge_store, query, await fake_embeddings.embed([query]), "legal", RetrieverConfig(top_k=2, mode="vector_only"), tenant_id=UUID(tenant_a.id))

    assert results[0]["document_id"] == "ccpa.md"
    assert 0.0 < results[0]["vector_score"] <= 1.0001
    assert results[0]["vector_score"] > results[1]["vector_score"]


async def test_bm25_only_matches_keywords_and_misses_unrelated_terms(knowledge_store, tenant_a, fake_embeddings, tmp_path):
    await _ingest_text(knowledge_store, fake_embeddings, tmp_path, "gdpr.md", GDPR, "legal", tenant_a)

    hit = await retrieve(knowledge_store, "supervisory", await fake_embeddings.embed(["supervisory"]), "legal", RetrieverConfig(mode="bm25_only"), tenant_id=UUID(tenant_a.id))
    miss = await retrieve(knowledge_store, "cryptocurrency", await fake_embeddings.embed(["cryptocurrency"]), "legal", RetrieverConfig(mode="bm25_only"), tenant_id=UUID(tenant_a.id))

    assert [r["document_id"] for r in hit] == ["gdpr.md"]
    assert miss == []

"""A11: with no fake installed, ingestion cannot reach a real embedding provider."""
from uuid import UUID

import pytest

from adapters.litellm_embeddings import LitellmEmbeddings
from core.pipeline.db_ingest import ingestion_pipeline
from tests.fakes import NetworkBlockedError


async def test_network_guard_blocks_ingestion_embedding_without_a_fake_and_writes_nothing(knowledge_store, owner_pool, tenant_a, tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Title\n\nSome text to embed.\n")

    with pytest.raises(NetworkBlockedError, match="litellm.aembedding"):
        await ingestion_pipeline(
            str(path), "doc.md", "legal", store=knowledge_store, embeddings=LitellmEmbeddings("ollama/nomic-embed-text", 768),
            tenant_id=UUID(tenant_a.id),
        )  # the real LiteLLM adapter, no fake_embeddings fixture

    assert await owner_pool.fetchval("SELECT count(*) FROM documents") == 0

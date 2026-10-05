"""One contract for every `KnowledgeStore`: Postgres with pgvector (as `gap_app`, row-level security on) and the
in-memory fake. Both must give the same answers."""
from types import SimpleNamespace
from uuid import UUID

import asyncpg
import pytest
from pgvector.asyncpg import register_vector

from adapters.pg_knowledge import PgKnowledgeStore
from ports import ChunkRow
from tests.db_fixtures import KB_DESCRIPTIONS as KBS  # the knowledge bases the `tenants` fixture creates
from tests.fakes import FakeKnowledgeStore, fake_embedding

MODEL, DIM = "test/model-a", 768
GDPR = "Personal data breach notification must reach the supervisory authority within 72 hours."
CCPA = "Consumers may request deletion of personal information held by a business."


ACTIVE = {"embedding_model": MODEL, "embedding_dim": DIM}


def chunk(text, filename="x.md"):
    return ChunkRow(content=text, embedding=fake_embedding(text), metadata={"source_filename": filename})


@pytest.fixture(params=["postgres", "fake"])
async def env(request):
    """`store` plus the ids of two tenants that each own the knowledge bases in KBS."""
    if request.param == "fake":
        a, b = UUID(int=1), UUID(int=2)
        yield SimpleNamespace(store=FakeKnowledgeStore({a: dict(KBS), b: dict(KBS)}), a=a, b=b)
        return
    app_url = request.getfixturevalue("app_database_url")
    tenant_a, tenant_b = request.getfixturevalue("tenant_a"), request.getfixturevalue("tenant_b")  # also clean the state
    pool = await asyncpg.create_pool(dsn=app_url, min_size=1, max_size=4, init=register_vector, statement_cache_size=0)
    try:
        yield SimpleNamespace(store=PgKnowledgeStore(pool), a=UUID(tenant_a.id), b=UUID(tenant_b.id))
    finally:
        await pool.close()


async def put(env, tenant, document_id, text, namespace="legal", model=MODEL, dim=DIM):
    await env.store.insert_chunks(tenant, document_id, namespace, [chunk(text, document_id)], embedding_model=model, embedding_dim=dim)


async def test_knowledge_bases_are_listed_by_slug_and_checked_by_existence(env):
    assert await env.store.list_knowledge_bases(env.a) == dict(sorted(KBS.items()))
    assert list(await env.store.list_knowledge_bases(env.a)) == ["default", "kyc_aml", "legal"]
    assert await env.store.kb_exists(env.a, "legal") is True
    assert await env.store.kb_exists(env.a, "no-such-kb") is False


async def test_vector_search_ranks_by_similarity_and_scores_are_cosines(env):
    await put(env, env.a, "gdpr.md", GDPR)
    await put(env, env.a, "ccpa.md", CCPA)
    query = "consumers deletion of personal information"
    hits = await env.store.search_vector(env.a, fake_embedding(query), "legal", 5, embedding_model=MODEL, embedding_dim=DIM)
    assert [h["document_id"] for h in hits][0] == "ccpa.md"
    assert 0.0 < hits[0]["vector_score"] <= 1.0001
    assert hits[0]["vector_score"] > hits[-1]["vector_score"] or len(hits) == 1
    assert hits[0]["source_filename"] == "ccpa.md" and hits[0]["metadata"] == {"source_filename": "ccpa.md"}
    assert {"id", "document_id", "content", "metadata", "vector_score", "source_filename"} <= set(hits[0])


async def test_vector_search_respects_the_limit_the_namespace_and_the_score_floor(env):
    await put(env, env.a, "gdpr.md", GDPR)
    await put(env, env.a, "ccpa.md", CCPA)
    await put(env, env.a, "bsa.md", "Banks must file suspicious activity reports.", namespace="kyc_aml")
    vec = fake_embedding(GDPR)
    assert len(await env.store.search_vector(env.a, vec, "legal", 1, embedding_model=MODEL, embedding_dim=DIM)) == 1
    assert [h["document_id"] for h in await env.store.search_vector(env.a, vec, "kyc_aml", 5, embedding_model=MODEL, embedding_dim=DIM)] == ["bsa.md"]
    assert await env.store.search_vector(env.a, vec, "default", 5, embedding_model=MODEL, embedding_dim=DIM) == []
    top = await env.store.search_vector(env.a, vec, "legal", 5, embedding_model=MODEL, embedding_dim=DIM, min_score=0.99)
    assert [h["document_id"] for h in top] == ["gdpr.md"]


async def test_vectors_of_another_model_or_dimension_are_ignored_and_counted_as_stale(env):
    await put(env, env.a, "gdpr.md", GDPR)
    await put(env, env.a, "old.md", GDPR, model="test/model-old")
    await put(env, env.b, "other-tenant-old.md", GDPR, model="test/model-old")
    vec = fake_embedding(GDPR)
    hits = await env.store.search_vector(env.a, vec, "legal", 10, embedding_model=MODEL, embedding_dim=DIM)
    assert [h["document_id"] for h in hits] == ["gdpr.md"]
    assert await env.store.search_vector(env.a, vec, "legal", 10, embedding_model=MODEL, embedding_dim=1536) == []
    # the text search skips the stale row too, though its words match: stale rows take part in no search
    assert [h["document_id"] for h in await env.store.search_bm25(env.a, "supervisory", "legal", 10, **ACTIVE)] == ["gdpr.md"]
    assert await env.store.count_stale_vectors(MODEL, DIM) == 2  # across tenants: it is a platform count
    assert await env.store.count_stale_vectors("test/model-old", DIM) == 1
    assert await env.store.count_stale_vectors(MODEL, 1536) == 3


async def test_bm25_matches_words_and_misses_unrelated_terms(env):
    await put(env, env.a, "gdpr.md", GDPR)
    hit = await env.store.search_bm25(env.a, "supervisory", "legal", 5, **ACTIVE)
    assert [h["document_id"] for h in hit] == ["gdpr.md"] and hit[0]["bm25_score"] > 0
    assert hit[0]["source_filename"] == "gdpr.md"
    assert await env.store.search_bm25(env.a, "cryptocurrency", "legal", 5, **ACTIVE) == []
    assert await env.store.search_bm25(env.a, "supervisory", "kyc_aml", 5, **ACTIVE) == []
    assert await env.store.search_bm25(env.a, "", "legal", 5, **ACTIVE) == []


async def test_a_short_bm25_query_needs_every_word_and_a_long_one_any_word(env):
    await put(env, env.a, "gdpr.md", GDPR)
    assert await env.store.search_bm25(env.a, "supervisory cryptocurrency", "legal", 5, **ACTIVE) == []  # AND below five words
    long = await env.store.search_bm25(env.a, "supervisory cryptocurrency lemonade pineapple banana", "legal", 5, **ACTIVE)
    assert [h["document_id"] for h in long] == ["gdpr.md"]  # OR from five words up


async def test_tenants_never_see_each_others_chunks_or_registry(env):
    await put(env, env.a, "gdpr.md", GDPR)
    await env.store.register_document(env.a, "gdpr.md", "legal", "h" * 64, 1, "gdpr.md")
    vec = fake_embedding(GDPR)
    assert await env.store.search_vector(env.b, vec, "legal", 5, embedding_model=MODEL, embedding_dim=DIM) == []
    assert await env.store.search_bm25(env.b, "supervisory", "legal", 5, **ACTIVE) == []
    assert await env.store.list_documents(env.b, None, None) == []
    assert await env.store.document_status(env.b, "gdpr.md", "legal", "h" * 64) == "new"
    assert await env.store.delete_document(env.b, "gdpr.md", "legal") == 0
    assert len(await env.store.search_bm25(env.a, "supervisory", "legal", 5, **ACTIVE)) == 1  # B's delete touched nothing


async def test_delete_document_removes_its_chunks_only_and_counts_them(env):
    await env.store.insert_chunks(env.a, "gdpr.md", "legal", [chunk(GDPR), chunk(GDPR + " Again.")], embedding_model=MODEL, embedding_dim=DIM)
    await put(env, env.a, "ccpa.md", CCPA)
    await put(env, env.a, "gdpr.md", GDPR, namespace="kyc_aml")
    assert await env.store.delete_document(env.a, "gdpr.md", "legal") == 2
    assert await env.store.delete_document(env.a, "gdpr.md", "legal") == 0
    vec = fake_embedding(GDPR)
    left = await env.store.search_vector(env.a, vec, "legal", 10, embedding_model=MODEL, embedding_dim=DIM)
    assert [h["document_id"] for h in left] == ["ccpa.md"]
    assert len(await env.store.search_vector(env.a, vec, "kyc_aml", 10, embedding_model=MODEL, embedding_dim=DIM)) == 1


async def test_document_status_follows_the_registry_new_unchanged_updated(env):
    assert await env.store.document_status(env.a, "gdpr.md", "legal", "1" * 64) == "new"
    await env.store.register_document(env.a, "gdpr.md", "legal", "1" * 64, 3, "gdpr.md")
    assert await env.store.document_status(env.a, "gdpr.md", "legal", "1" * 64) == "unchanged"
    assert await env.store.document_status(env.a, "gdpr.md", "legal", "2" * 64) == "updated"
    assert await env.store.document_status(env.a, "gdpr.md", "kyc_aml", "1" * 64) == "new"  # per namespace
    await env.store.register_document(env.a, "gdpr.md", "legal", "2" * 64, 4, "gdpr-v2.md")  # an upsert
    docs = await env.store.list_documents(env.a, "legal", None)
    assert [(d.document_id, d.content_hash, d.chunk_count, d.source_filename) for d in docs] == [("gdpr.md", "2" * 64, 4, "gdpr-v2.md")]


async def test_list_documents_is_newest_first_and_filters_by_namespace_and_visible_kbs(env):
    await env.store.register_document(env.a, "first.md", "legal", "a" * 64, 1, "first.md")
    await env.store.register_document(env.a, "second.md", "kyc_aml", "b" * 64, 2, "second.md")
    await env.store.register_document(env.a, "third.md", "default", "c" * 64, 3, "third.md")
    assert [d.document_id for d in await env.store.list_documents(env.a, None, None)] == ["third.md", "second.md", "first.md"]
    assert [d.document_id for d in await env.store.list_documents(env.a, "kyc_aml", None)] == ["second.md"]
    assert [d.document_id for d in await env.store.list_documents(env.a, None, ["legal", "default"])] == ["third.md", "first.md"]
    assert await env.store.list_documents(env.a, "kyc_aml", ["legal"]) == []
    assert (await env.store.list_documents(env.a, "legal", None))[0].last_ingested_at is not None

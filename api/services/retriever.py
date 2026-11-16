"""
api/services/retriever.py

Production-ready hybrid retriever service.
Called by the /search route and by LangGraph agents.
"""
import asyncio
from dataclasses import dataclass
from uuid import UUID

import config
from ports import Embeddings, KnowledgeStore


@dataclass
class RetrieverConfig:
    top_k: int = 5
    rrf_k: int = 60
    # Compatibility names: the keyword leg uses Postgres full-text ts_rank ranking.
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    mode: str = "hybrid"

def rrf_merge(
    bm25_results: list[dict],
    vector_results: list[dict],
    k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}  # document_id mapped to best available fields

    for rank, doc in enumerate(bm25_results, start=1):
        chunk_id = doc["id"]
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
        docs.setdefault(chunk_id, doc)  # keep first seen (bm25) unless overwritten below

    for rank, doc in enumerate(vector_results, start=1):
        chunk_id = doc["id"]
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
        docs[chunk_id] = doc  # vector fields win on overlap, per spec

    merged = []
    for chunk_id, rrf_score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]:
        entry = dict(docs[chunk_id])
        entry["rrf_score"] = rrf_score
        merged.append(entry)

    return merged


async def retrieve(
    store: KnowledgeStore,
    query: str,
    query_embedding: Embeddings,
    namespace: str,
    cfg: RetrieverConfig | None = None,
    *,
    tenant_id: UUID,
) -> list[dict]:
    if cfg is None:
        cfg = RetrieverConfig()

    async def vector(limit: int) -> list[dict]:
        # Only vectors from the query's own model and dimension are compared (Sprint 006).
        return await store.search_vector(
            tenant_id, query_embedding.vectors[0], namespace, limit,
            embedding_model=query_embedding.model, embedding_dim=query_embedding.dim, min_score=config.MIN_VECTOR_SCORE,
        )

    async def bm25(limit: int) -> list[dict]:
        # Stale rows (another embedding model) take part in no search, text or vector.
        return await store.search_bm25(
            tenant_id, query, namespace, limit,
            embedding_model=query_embedding.model, embedding_dim=query_embedding.dim,
        )

    if cfg.mode == "vector_only":
        candidates = await vector(cfg.top_k)

    elif cfg.mode == "bm25_only":
        candidates = await bm25(cfg.top_k)

    elif cfg.mode == "hybrid":
        over_fetch = cfg.top_k * 2
        bm25_results, vector_results = await asyncio.gather(
            bm25(over_fetch),
            vector(over_fetch),
        )
        candidates = rrf_merge(
            bm25_results, vector_results,
            k=cfg.rrf_k,
            top_k=cfg.top_k,
        )

    else:
        raise ValueError(f"Unknown retrieval mode: {cfg.mode}")

    return candidates[:cfg.top_k]

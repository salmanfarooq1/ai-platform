"""
api/services/retriever.py

Production-ready hybrid retriever service.
Called by the /search route and by LangGraph agents.
"""
import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import config
from core.processing.cpu_offload import run_cpu_bound
from ports import Embeddings, KnowledgeStore


@dataclass
class RetrieverConfig:
    top_k: int = 5
    rrf_k: int = 60
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    mode: str = "hybrid"
    rerank: bool = False          # turn reranking on/off
    rerank_candidates: int = 20   # how many candidates to feed the reranker

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

# Typed as Any rather than CrossEncoder: sentence-transformers pulls in torch
# (~2GB installed, ~300MB resident just to import), which does not fit the
# 512MB free-tier memory budget. It is not installed in the production image
# and is imported lazily below, so it must not be referenced at module scope.
_cross_encoder: Any = None

def get_cross_encoder() -> Any:
    """
    Module-level singleton — loads the model once per process.

    ProcessPoolExecutor reuses worker processes across calls (it does NOT
    spawn a new process per task). So this model loads exactly once per
    worker on the first rerank() call into that worker, then stays in RAM
    for all subsequent calls to the same worker. With max_workers=1 (the
    default in run_cpu_bound), it loads exactly once for the lifetime of
    the pool.

    Consequence: the ~380ms cold-load cost (confirmed in lab C.5) is paid
    once at startup, not on every request.
    """
    global _cross_encoder
    if _cross_encoder is None:
        # Imported here, not at module scope, so that deployments with
        # FEATURES["reranker_enabled"] = False never pay the torch import cost
        # and can ship an image without sentence-transformers installed.
        from sentence_transformers import CrossEncoder

        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    if not candidates:
        return []

    model = get_cross_encoder()
    pairs = [(query, c["content"]) for c in candidates]
    scores = model.predict(pairs)

    for c, score in zip(candidates, scores):
        c["rerank_score"] = float(score)

    ranked = sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)
    return ranked[:top_k]


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
        over_fetch = cfg.rerank_candidates if cfg.rerank else cfg.top_k * 2
        bm25_results, vector_results = await asyncio.gather(
            bm25(over_fetch),
            vector(over_fetch),
        )
        candidates = rrf_merge(
            bm25_results, vector_results,
            k=cfg.rrf_k,
            top_k=cfg.rerank_candidates if cfg.rerank else cfg.top_k,
        )

    else:
        raise ValueError(f"Unknown retrieval mode: {cfg.mode}")

    # Rerank if enabled and there is more than one candidate to reorder.
    # Previous condition (len > top_k) skipped reranking when few candidates
    # existed. The cross encoder should run whenever there is a choice to make.
    if cfg.rerank and len(candidates) > 1:
        candidates = await run_cpu_bound(rerank, query, candidates, cfg.top_k)

    return candidates[:cfg.top_k]

"""
api/services/retriever.py

Production-ready hybrid retriever service.
Called by the /search route and by LangGraph agents.
"""
import asyncio
import json
from dataclasses import dataclass

from asyncpg import Pool
from sentence_transformers import CrossEncoder

import config
from core.processing.cpu_offload import run_cpu_bound


def _parse_metadata(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or {}


@dataclass
class RetrieverConfig:
    top_k: int = 5
    rrf_k: int = 60
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    mode: str = "hybrid"
    rerank: bool = False          # turn reranking on/off
    rerank_candidates: int = 20   # how many candidates to feed the reranker

BM25_OR_THRESHOLD = 5  # queries with 5 or more words switch AND to OR

async def retrieve_bm25(
    pool: Pool,
    query: str,
    namespace: str,
    limit: int,
) -> list[dict]:
    word_count = len(query.split())
    use_or_mode = word_count >= BM25_OR_THRESHOLD

    async with pool.acquire() as conn:
        if use_or_mode:
            tsq = await conn.fetchval(
                "SELECT replace(plainto_tsquery('english', $1)::text, '&', '|')::tsquery", query
            )
        else:
            tsq = await conn.fetchval(
                "SELECT plainto_tsquery('english', $1)", query
            )

        if not str(tsq):
            return []

        rows = await conn.fetch(
            """
            SELECT id, document_id, content, metadata,
                   ts_rank(fts_vector, $1) AS bm25_score
            FROM documents
            WHERE namespace = $2 AND fts_vector @@ $1
            ORDER BY bm25_score DESC
            LIMIT $3
            """,
            tsq, namespace, limit,
        )

    results = []
    for r in rows:
        meta = _parse_metadata(r["metadata"])
        results.append({
            "id": r["id"],
            "document_id": r["document_id"],
            "content": r["content"],
            "metadata": meta,
            "bm25_score": r["bm25_score"],
            "source_filename": meta.get("source_filename"),
        })
    return results


async def retrieve_vector(
    pool: Pool,
    query_embedding: list[float],
    namespace: str,
    limit: int,
    min_score: float = config.MIN_VECTOR_SCORE,
) -> list[dict]:
    """
    Vector similarity search with a score floor.

    Why the nested SQL query (SELECT * FROM (SELECT ...))?
    Postgres processes the WHERE clause before it processes the SELECT clause.
    If we calculate the vector_score inside the SELECT, Postgres doesn't know what 
    "vector_score" is when it hits the WHERE clause, unless we type the whole math formula again!
    
    To avoid making the database do the math twice, we use a subquery:
    1. The inner query does the math once and labels it 'vector_score'.
    2. The outer query can now safely filter using WHERE vector_score > min_score.
    
    min_score defaults to config.MIN_VECTOR_SCORE (0.0) so we don't break existing code.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM (
                SELECT id, document_id, content, metadata,
                       1.0 - (embedding <=> $1::vector) AS vector_score
                FROM documents
                WHERE namespace = $2
            ) scored
            WHERE vector_score > $4
            ORDER BY vector_score DESC
            LIMIT $3
            """,
            query_embedding, namespace, limit, min_score,
        )

    results = []
    for r in rows:
        meta = _parse_metadata(r["metadata"])
        results.append({
            "id": r["id"],
            "document_id": r["document_id"],
            "content": r["content"],
            "metadata": meta,
            "vector_score": r["vector_score"],
            "source_filename": meta.get("source_filename"),
        })
    return results


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

_cross_encoder: CrossEncoder | None = None

def get_cross_encoder() -> CrossEncoder:
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
    pool: Pool,
    query: str,
    query_embedding: list[float],
    namespace: str,
    cfg: RetrieverConfig | None = None,
) -> list[dict]:
    if cfg is None:
        cfg = RetrieverConfig()

    if cfg.mode == "vector_only":
        candidates = await retrieve_vector(pool, query_embedding, namespace, cfg.top_k)

    elif cfg.mode == "bm25_only":
        candidates = await retrieve_bm25(pool, query, namespace, cfg.top_k)

    elif cfg.mode == "hybrid":
        over_fetch = cfg.rerank_candidates if cfg.rerank else cfg.top_k * 2
        bm25_results, vector_results = await asyncio.gather(
            retrieve_bm25(pool, query, namespace, over_fetch),
            retrieve_vector(pool, query_embedding, namespace, over_fetch),
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

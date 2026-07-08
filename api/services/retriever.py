"""
api/services/retriever.py

Production-ready hybrid retriever service.
Called by the /search route and by LangGraph agents.
"""
import asyncio
from dataclasses import dataclass
from asyncpg import Pool
import config
import json

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
    mode: str = "hybrid"  # "vector_only" | "bm25_only" | "hybrid"


BM25_OR_THRESHOLD = 5  # queries with 5+ words switch AND -> OR

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
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, document_id, content, metadata,
                   1.0 - (embedding <=> $1::vector) AS vector_score
            FROM documents
            WHERE namespace = $2
            ORDER BY vector_score DESC
            LIMIT $3
            """,
            query_embedding, namespace, limit,
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
    docs: dict[str, dict] = {}  # document_id -> best available fields

    for rank, doc in enumerate(bm25_results, start=1):
        chunk_id = doc["id"]
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
        docs.setdefault(chunk_id, doc)  # keep first-seen (bm25) unless overwritten below

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
    pool: Pool,
    query: str,
    query_embedding: list[float],
    namespace: str,
    config: RetrieverConfig | None = None,
) -> list[dict]:
    if config is None:
        config = RetrieverConfig()

    if config.mode == "vector_only":
        results = await retrieve_vector(pool, query_embedding, namespace, config.top_k)
        return results[: config.top_k]

    if config.mode == "bm25_only":
        results = await retrieve_bm25(pool, query, namespace, config.top_k)
        return results[: config.top_k]
    

    if config.mode == "hybrid":
        over_fetch = config.top_k * 2
        bm25_results, vector_results = await asyncio.gather(
            retrieve_bm25(pool, query, namespace, over_fetch),
            retrieve_vector(pool, query_embedding, namespace, over_fetch),
        )
        return rrf_merge(bm25_results, vector_results, k=config.rrf_k, top_k=config.top_k)

    raise ValueError(f"Unknown retrieval mode: {config.mode}")
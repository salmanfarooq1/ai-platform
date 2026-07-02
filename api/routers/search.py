from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from asyncpg import Pool
import litellm
from api.models.schemas import SearchRequest, SearchResponse, SearchResult
from api.services.llm import generate_with_routing
from api.services.cache import (
    get_cached_response,
    set_cached_response,
    semantic_cache_lookup,
    semantic_cache_store,
    embed_query,
)
from config import LLM_CONFIG

router = APIRouter()


async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool


@router.post("/search", response_model=SearchResponse)
async def search(
    request: Request,
    payload: SearchRequest,
    pool: Pool = Depends(get_db_pool),
):
    # ── Step 1: Exact cache check ─────────────────────────────────────────
    # Cheapest possible check — pure Redis GET, no embedding, no DB, no LLM.
    # If this hits, we're done in ~1ms.
    exact_hit = await get_cached_response(payload.query, payload.namespace, payload.top_k)
    if exact_hit:
        request.state.usage = {"cache": "exact_hit", "total_cost": 0.0}
        response = JSONResponse(content=exact_hit)
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Cache-Type"] = "exact"
        response.headers["X-Cost-USD"] = "0.000000"
        return response

    # ── Step 2: Embed query ───────────────────────────────────────────────
    # Embedding is needed for both semantic cache lookup AND vector search.
    # Compute once, use twice — don't embed twice.
    try:
        query_embedding = await embed_query(payload.query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding provider failed: {str(e)}")

    # ── Step 3: Semantic cache check ──────────────────────────────────────
    # Slightly more expensive than exact (vector search in Redis) but still
    # orders of magnitude cheaper than a DB + LLM round trip.
    semantic_hit = await semantic_cache_lookup(payload.query, payload.namespace, query_embedding)
    if semantic_hit:
        request.state.usage = {"cache": "semantic_hit", "total_cost": 0.0}
        response = JSONResponse(content=semantic_hit)
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Cache-Type"] = "semantic"
        response.headers["X-Cost-USD"] = "0.000000"
        return response

    # ── Step 4: Full pipeline — cache miss ────────────────────────────────
    query_sql = """
        SELECT document_id, namespace, content, metadata,
               embedding <=> $1::vector AS distance
        FROM documents
        WHERE namespace = $2
        ORDER BY distance ASC
        LIMIT $3;
    """

    async with pool.acquire() as conn:
        records = await conn.fetch(
            query_sql,
            query_embedding,
            payload.namespace,
            payload.top_k,
        )

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No documents found in namespace '{payload.namespace}'. Ingest documents first."
        )

    db_chunks = [
        {
            "document_id": r["document_id"],
            # metadata is a JSON string from asyncpg — parse it
            "source_filename": (
                r["metadata"].get("filename", "unknown")
                if isinstance(r["metadata"], dict)
                else "unknown"
            ),
            "text": r["content"],
            "score": 1.0 - float(r["distance"]),
        }
        for r in records
    ]

    try:
        # generate_with_routing classifies complexity, picks model, generates
        answer_obj, usage_dict = await generate_with_routing(payload.query, db_chunks)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM provider failed: {str(e)}")

    # Attach usage to request state — FinOps middleware reads this
    request.state.usage = usage_dict

    # Build response dict — stored in both caches
    results = [
        SearchResult(
            document_id=c.document_id,
            namespace=payload.namespace,
            content=c.excerpt,
            score=c.relevance_score,
            metadata={"chunk_index": c.chunk_index},
        )
        for c in answer_obj.citations
    ]

    response_data = SearchResponse(
        query=payload.query,
        answer=answer_obj.answer,
        confidence=answer_obj.confidence,
        needs_clarification=answer_obj.needs_clarification,
        results=results,
        total_results=len(results),
    ).model_dump()

    # ── Step 5: Store in both caches ──────────────────────────────────────
    # Fire-and-forget — cache writes never block the response
    await set_cached_response(payload.query, payload.namespace, payload.top_k, response_data)
    await semantic_cache_store(payload.query, payload.namespace, query_embedding, response_data)

    response = JSONResponse(content=response_data)
    response.headers["X-Cache"] = "MISS"
    response.headers["X-Cache-Type"] = "none"
    response.headers["X-Cost-USD"] = f"{usage_dict.get('total_cost', 0.0):.6f}"
    return response
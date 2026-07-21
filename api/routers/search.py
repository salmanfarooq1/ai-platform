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
from api.services.retriever import retrieve, RetrieverConfig
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
    # Step 1: Exact cache check 
    # Cheapest possible check with pure Redis GET, no embedding, no DB, no LLM.
    # If this hits, we're done in ~1ms.
    exact_hit = await get_cached_response(payload.query, payload.namespace, payload.top_k)
    if exact_hit:
        request.state.usage = {"cache": "exact_hit", "total_cost": 0.0}
        response = JSONResponse(content=exact_hit)
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Cache-Type"] = "exact"
        response.headers["X-Cost-USD"] = "0.000000"
        return response

    # Step 2: Embed query 
    # Embedding is needed for both semantic cache lookup AND vector search.
    # Compute once, use twice but don't embed twice.
    try:
        query_embedding = await embed_query(payload.query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding provider failed: {str(e)}")

    # Step 3: Semantic cache check 
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

    # Step 4: Full pipeline on cache MISS — hybrid retrieval + LLM generation
    retriever_config = RetrieverConfig(
        top_k=payload.top_k,
        mode="hybrid",
        rerank=True,  # C.5: confirmed safe via lab_7.5_rerank_event_loop.py
    )

    raw_chunks = await retrieve(
        pool=pool,
        query=payload.query,
        query_embedding=query_embedding,
        namespace=payload.namespace,
        config=retriever_config,
    )

    if not raw_chunks:
        raise HTTPException(
            status_code=404,
            detail=f"No documents found in namespace '{payload.namespace}'. Ingest documents first."
        )

    # Normalise retriever output to the shape generate_with_routing expects:
    # keys: document_id, source_filename, text, score
    db_chunks = [
        {
            "document_id": c["document_id"],
            "source_filename": c.get("source_filename") or "unknown",
            "text": c["content"],
            # Use explicit key-existence checks, NOT Python `or`.
            # `or` treats 0.0 as falsy and would fall through to the next score
            # even when 0.0 is a legitimate value. rrf_score is always a small
            # positive float (1/(k+rank)), so it can never be zero in practice,
            # but this pattern is correct for any future score field.
            # NOTE: rerank_score is intentionally excluded here. It is a raw
            # cross-encoder logit (unbounded, not in [0,1]) — not comparable
            # to vector_score or rrf_score. Displaying it as a confidence
            # percentage would be misleading. Reranking only changes ordering.
            "score": (
                c["rrf_score"]    if "rrf_score"    in c else
                c["vector_score"] if "vector_score" in c else
                c["bm25_score"]   if "bm25_score"   in c else
                0.0
            ),
        }
        for c in raw_chunks
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

    # Step 5: Store in both caches 
    # Fire-and-forget pattern here so that cache writes never block the response
    await set_cached_response(payload.query, payload.namespace, payload.top_k, response_data)
    await semantic_cache_store(payload.query, payload.namespace, query_embedding, response_data)

    response = JSONResponse(content=response_data)
    response.headers["X-Cache"] = "MISS"
    response.headers["X-Cache-Type"] = "none"
    response.headers["X-Cost-USD"] = f"{usage_dict.get('total_cost', 0.0):.6f}"
    return response
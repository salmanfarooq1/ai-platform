import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.auth import require_kb, require_scope
from api.dependencies import adapters_of
from api.gateway_deps import entry_action, gateway_context
from api.models.schemas import SearchRequest, SearchResponse, SearchResult
from api.services.cache import (
    get_cached_response,
    semantic_cache_lookup,
    semantic_cache_store,
    set_cached_response,
)
from api.services.llm import GENERATION_MAX_TOKENS, generate_with_routing
from api.services.model_calls import ModelCallFailed, build_model_caller
from api.services.retriever import RetrieverConfig, retrieve
from config import LLM_CONFIG, completion_fallbacks_for_mode
from core.identity.models import Principal, Scope
from core.settings import get_settings
from gateway import ActionKind, EnforcementContext, GatewayDenied, check_output, require
from gateway.estimate import estimate_tokens
from ports.models import ModelUse

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(
    request: Request,
    payload: SearchRequest,
    principal: Principal = Depends(require_scope(Scope.QUERY)),
    ctx: EnforcementContext = Depends(gateway_context),
):
    tenant_id = principal.tenant_id
    adapters = adapters_of(request)

    # Step -1: the gateway decides first: scope and policy for this KB, input guardrails, rate limit and
    # daily token budget. A denial is a 403 (policy), 400 (guardrail), 429 (limits) or 503 (Redis down).
    await require(ctx, entry_action(request.url.path, ActionKind.KB_READ, payload.namespace, input_text=payload.query))

    # Step -0.5: the knowledge base must be one of the caller's own (404 otherwise, no existence leak)
    await require_kb(adapters.knowledge, principal, payload.namespace)

    # Step 0: the model that will answer must be allowed, checked before any cache, embedding or LLM I/O.
    settings = get_settings()
    completion_caller = build_model_caller(adapters, settings, adapters.llm)
    embedding_caller = build_model_caller(adapters, settings, adapters.embeddings)
    # Admit both model families before query embedding, which is the first possible inference.
    completion_aliases = (LLM_CONFIG["model"], *completion_fallbacks_for_mode(settings.mode))
    for alias in completion_aliases:
        await completion_caller.admit(
            ctx, alias, ModelUse.COMPLETION, input_text=payload.query,
            estimated_tokens=estimate_tokens(payload.query, GENERATION_MAX_TOKENS),
        )
    embedding_aliases = (str(settings.embed_model), *settings.embed_fallbacks)
    await embedding_caller.admit(
        ctx, embedding_aliases[0], ModelUse.EMBEDDING, input_text=payload.query,
    )
    for alias in embedding_aliases[1:]:
        await embedding_caller.admit(ctx, alias, ModelUse.EMBEDDING, input_text=payload.query)

    # Embed before cache lookup so cache identity comes from the resolved model that answered.
    # Embedding is needed for both semantic cache lookup AND vector search.
    # Compute once, use twice but don't embed twice.
    try:
        query_embedding = await embedding_caller.embed(
            ctx, str(settings.embed_model), [payload.query], input_text=payload.query,
        )
    except GatewayDenied:
        raise
    except Exception as exc:
        if isinstance(exc, ModelCallFailed) and exc.category == "dimension_mismatch":
            raise HTTPException(status_code=502, detail=(
                f"Embedding provider {exc.alias} refused: expected width {exc.expected_dim}, "
                f"returned width {exc.returned_dim}"
            )) from None
        raise HTTPException(status_code=502, detail="Embedding provider failed") from None

    exact_hit = await get_cached_response(
        adapters.cache, tenant_id, payload.query, payload.namespace, payload.top_k,
        payload.retrieval_mode, query_embedding.model,
    )
    if exact_hit:
        request.state.usage = {"cache": "exact_hit", "total_cost": 0.0, "namespace": payload.namespace}
        response = JSONResponse(content=exact_hit)
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Cache-Type"] = "exact"
        response.headers["X-Cost-USD"] = "0.000000"
        return response

    # Step 3: Semantic cache check
    # Slightly more expensive than exact (vector search in Redis) but still
    # orders of magnitude cheaper than a DB + LLM round trip.
    semantic_hit = await semantic_cache_lookup(
        adapters.cache, tenant_id, payload.query, payload.namespace, query_embedding.vectors[0],
        payload.retrieval_mode, payload.top_k,
        query_embedding.model,
    )
    if semantic_hit:
        request.state.usage = {"cache": "semantic_hit", "total_cost": 0.0, "namespace": payload.namespace}
        response = JSONResponse(content=semantic_hit)
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Cache-Type"] = "semantic"
        response.headers["X-Cost-USD"] = "0.000000"
        return response

    # Step 4: Full pipeline on cache MISS — hybrid retrieval + LLM generation
    retriever_config = RetrieverConfig(
        top_k=payload.top_k,
        mode=payload.retrieval_mode,
    )

    raw_chunks = await retrieve(
        store=adapters.knowledge,
        query=payload.query,
        query_embedding=query_embedding,
        namespace=payload.namespace,
        cfg=retriever_config,
        tenant_id=tenant_id,
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
        answer_obj, usage_dict = await generate_with_routing(
            adapters.llm, payload.query, db_chunks, caller=completion_caller, ctx=ctx,
        )
    except GatewayDenied:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="LLM provider failed") from None

    # Attach usage to request state — FinOps middleware reads this
    request.state.usage = usage_dict
    request.state.usage["namespace"] = payload.namespace

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

    # Step 4.5: Output guardrail check — evaluate LLM confidence floor
    output_guard = check_output(answer_obj.answer, answer_obj.confidence)

    response_data = SearchResponse(
        query=payload.query,
        answer=answer_obj.answer,
        confidence=answer_obj.confidence,
        needs_clarification=getattr(answer_obj, "needs_clarification", False),
        rerank_applied=False,
        results=results,
        total_results=len(results),
        flagged=output_guard.flagged,
        flag_reason=output_guard.flag_reason,
    ).model_dump()

    # Step 5: Store in both caches
    # Fire-and-forget: create_task schedules the writes on the event loop
    # without blocking the response. If Redis is down, the functions log
    # a warning internally and swallow the error.
    asyncio.create_task(set_cached_response(
        adapters.cache, tenant_id, payload.query, payload.namespace, payload.top_k, response_data,
        payload.retrieval_mode, query_embedding.model,
    ))
    asyncio.create_task(semantic_cache_store(
        adapters.cache, tenant_id, payload.query, payload.namespace, query_embedding.vectors[0], response_data,
        payload.retrieval_mode, payload.top_k,
        query_embedding.model,
    ))

    response = JSONResponse(content=response_data)
    response.headers["X-Cache"] = "MISS"
    response.headers["X-Cache-Type"] = "none"
    response.headers["X-Cost-USD"] = f"{usage_dict.get('total_cost', 0.0):.6f}"
    return response

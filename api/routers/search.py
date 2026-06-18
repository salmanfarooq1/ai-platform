from fastapi import APIRouter, Depends, Request, HTTPException
from asyncpg import Pool
import litellm
from api.models.schemas import SearchRequest, SearchResponse, SearchResult
from api.services.llm import generate_with_citations
from config import LLM_CONFIG

router = APIRouter()

async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool

@router.post("/search", response_model=SearchResponse)
async def search(
    request: Request,
    payload: SearchRequest,
    pool: Pool = Depends(get_db_pool)
):
    # 1. REAL EMBEDDING: Embed the user's query
    try:
        embed_response = await litellm.aembedding(
            model=LLM_CONFIG["embedding_model"],
            input=[payload.query]
        )
        query_embedding = embed_response.data[0]["embedding"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding Provider failed: {str(e)}")
    
    # 2. Vector Similarity Search (<-> is pgvector's Euclidean distance operator)
    query_sql = """
        SELECT document_id, namespace, content, metadata,
               embedding <-> $1::vector AS distance
        FROM documents
        WHERE namespace = $2
        ORDER BY distance ASC
        LIMIT $3;
    """
    
    async with pool.acquire() as conn:
        records = await conn.fetch(query_sql, query_embedding, payload.namespace, payload.top_k)
        
    db_chunks = [
        {
            "document_id": r["document_id"],
            "source_filename": r["metadata"].get("header_path", "unknown") if r["metadata"] else "unknown",
            "text": r["content"],
            "score": 1.0 - (r["distance"] / 100.0) 
        }
        for r in records
    ]
    
    # 3. Call our LLM Service! (Groq or Llama)
    try:
        answer_obj, usage_dict = await generate_with_citations(payload.query, db_chunks)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM Provider failed: {str(e)}")

    # 4. FINOPS MAGIC: Attach the tokens to the request!
    request.state.usage = usage_dict
    
    # 5. Format and return the final response
    results = [
        SearchResult(
            document_id=c.document_id,
            namespace=payload.namespace,
            content=c.excerpt,
            score=c.relevance_score,
            metadata={"chunk_index": c.chunk_index}
        )
        for c in answer_obj.citations
    ]
    
    return SearchResponse(
        query=payload.query,
        answer=answer_obj.answer,
        confidence=answer_obj.confidence,
        needs_clarification=answer_obj.needs_clarification,
        results=results,
        total_results=len(results)
    )
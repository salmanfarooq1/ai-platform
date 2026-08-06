"""
MCP tool definitions.

Tools are executable functions an MCP client (Claude Desktop, Cursor,
VS Code) can invoke remotely. Each tool receives the database pool
through the server's context dependency dict, not through function
arguments, so the caller never has to know about connection management.
"""
import json
import logging
from typing import Any

from asyncpg import Pool

from api.mcp.server import mcp
from api.models.schemas import IngestionStatusResponse, LatestDocumentInfo
from api.services.cache import embed_query
from api.services.guardrails import check_input
from api.services.retriever import RetrieverConfig, retrieve
from config import FEATURES, NAMESPACE_REGISTRY

logger = logging.getLogger("api.mcp.tools")


@mcp.tool()
async def list_namespaces() -> str:
    """Return available document namespaces and what each contains.

    Call this before searching if you are not sure which namespace
    holds the regulation you need. The response is a JSON object
    mapping each namespace name to a description of its contents.
    """
    return json.dumps(NAMESPACE_REGISTRY, indent=2)


@mcp.tool()
async def search_documents(
    query: str,
    namespace: str = "default",
    top_k: int = 5,
    mode: str = "hybrid",
) -> str:
    """Search the compliance document database for chunks matching a query.

    Args:
        query: Natural language description of what you need.
        namespace: Document scope (use list_namespaces to discover).
        top_k: Number of results (1-20).
        mode: "hybrid" (default), "vector_only", or "bm25_only".

    Returns:
        JSON with matched chunks including content, scores, and metadata.
    """
    guard = check_input(query)
    if guard.blocked:
        return json.dumps({"error": "query_blocked", "reason": guard.blocked_reason})

    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    try:
        k = max(1, min(top_k, 20))
        query_embedding = await embed_query(query)
        cfg = RetrieverConfig(
            top_k=k,
            mode=mode,
            rerank=FEATURES.get("reranker_enabled", False),
        )
        chunks = await retrieve(
            pool=pool,
            query=query,
            query_embedding=query_embedding,
            namespace=namespace,
            cfg=cfg,
        )

        if not chunks:
            return json.dumps({"count": 0, "result": "No relevant chunks found"})

        results = []
        for i, c in enumerate(chunks):
            if "rrf_score" in c and c["rrf_score"] is not None:
                score = c["rrf_score"]
            elif "vector_score" in c and c["vector_score"] is not None:
                score = c["vector_score"]
            else:
                score = c.get("bm25_score", 0.0)

            results.append({
                "chunk_index": i,
                "document_id": c["document_id"],
                "source_filename": c.get("source_filename", "unknown"),
                "score": round(float(score), 4),
                "content": c["content"][:800],
            })

        return json.dumps({"count": len(results), "chunks": results}, indent=2)

    except Exception as e:
        logger.error("[mcp/search] %s", e)
        return json.dumps({"error": str(e)})


@mcp.tool()
async def multi_namespace_search(
    query: str,
    namespaces: list[str] | None = None,
    top_k: int = 3,
) -> str:
    """Search across multiple namespaces and merge results.

    Use this for cross-regulation comparisons like "Compare GDPR and
    CCPA breach notification timelines". Searches each namespace
    independently and returns combined results sorted by score.

    Args:
        query: Natural language question.
        namespaces: List of namespaces to search. Defaults to all known.
        top_k: Results per namespace (1-10).
    """
    targets = namespaces or list(NAMESPACE_REGISTRY.keys())
    all_results = []

    for ns in targets:
        raw = await search_documents(query=query, namespace=ns, top_k=top_k)
        data = json.loads(raw)
        if "error" in data:
            return raw
        for chunk in data.get("chunks", []):
            chunk["namespace"] = ns
            all_results.append(chunk)

    all_results.sort(key=lambda c: c.get("score", 0), reverse=True)
    return json.dumps({"count": len(all_results), "chunks": all_results}, indent=2)


@mcp.tool()
async def get_ingestion_status(
    namespace: str = "default",
) -> str:
    """Check how many documents and chunks exist in a namespace.

    Returns document count, total chunk count, and the most recently
    ingested document. Useful for verifying that a corpus has been
    loaded before running searches against it.
    """
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    try:
        async with pool.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT document_id) AS doc_count,
                    COUNT(*) AS chunk_count
                FROM documents
                WHERE namespace = $1
                """,
                namespace,
            )
            latest = await conn.fetchrow(
                """
                SELECT document_id, source_filename, last_ingested_at
                FROM document_registry
                WHERE namespace = $1
                ORDER BY last_ingested_at DESC
                LIMIT 1
                """,
                namespace,
            )

        latest_info: LatestDocumentInfo | None = None
        if latest:
            latest_info = LatestDocumentInfo(
                document_id=latest["document_id"],
                source_filename=latest["source_filename"],
                ingested_at=latest["last_ingested_at"].isoformat(),
            )

        result = IngestionStatusResponse(
            namespace=namespace,
            document_count=stats["doc_count"],
            chunk_count=stats["chunk_count"],
            latest_document=latest_info,
        )
        return result.model_dump_json(indent=2)

    except Exception as e:
        logger.error("[mcp/ingestion_status] %s", e)
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_cost_summary(
    days: int = 7,
) -> str:
    """Get LLM cost summary for recent days.

    Returns per-day breakdown of token usage and dollar cost.
    Useful for monitoring spend before it hits budget limits.

    Args:
        days: Number of days to look back (1-30, default 7).
    """
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    try:
        d = max(1, min(days, 30))
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    DATE(created_at) AS day,
                    endpoint,
                    SUM(prompt_tokens) AS total_prompt,
                    SUM(completion_tokens) AS total_completion,
                    SUM(cost_usd) AS total_cost,
                    COUNT(*) AS request_count
                FROM usage_log
                WHERE created_at >= NOW() - MAKE_INTERVAL(days => $1)
                GROUP BY DATE(created_at), endpoint
                ORDER BY day DESC, endpoint
                """,
                d,
            )

        result = [
            {
                "date": r["day"].isoformat(),
                "endpoint": r["endpoint"],
                "prompt_tokens": r["total_prompt"],
                "completion_tokens": r["total_completion"],
                "cost_usd": float(r["total_cost"]),
                "requests": r["request_count"],
            }
            for r in rows
        ]

        return json.dumps({"days": d, "breakdown": result}, indent=2)

    except Exception as e:
        logger.error("[mcp/cost_summary] %s", e)
        return json.dumps({"error": str(e)})

import json
import logging
from typing import Literal

from asyncpg import Pool
from langchain_core.tools import tool

from api.services.cache import embed_query
from api.services.retriever import RetrieverConfig, retrieve
from config import FEATURES, NAMESPACE_REGISTRY

logger = logging.getLogger("api.agent.tools")


@tool
def list_namespaces() -> str:
    """
    List the document namespaces available to search, with a short
    description of what each one contains.

    Call this if you are unsure which namespace fits the question, instead
    of guessing (namespaces change over time as new document sets are
    added, so do not assume the ones you have seen before are the full list).

    Returns:
        JSON string mapping namespace name to a description.
    """
    return json.dumps(NAMESPACE_REGISTRY)


def make_retrieve_tool(pool: Pool):
    """
    Build the retrieve_chunks tool bound to a specific DB pool.

    Built as a closure instead of a module-level global flipped by a
    set_db_pool() call on every request so the tool is constructed once,
    at app startup, alongside the graph. Avoids mutable module state
    shared across concurrent requests, and is trivially testable: pass in
    a fake pool, no monkeypatching a global.
    """

    @tool
    async def retrieve_chunks(
        query: str,
        namespace: str = "default",
        top_k: int = 5,
        mode: Literal["hybrid", "vector_only", "bm25_only"] = "hybrid",
    ) -> str:
        """
        Search the compliance document database for chunks relevant to a query.

        Use this tool when you need to find specific regulatory text, policy content,
        or compliance documentation. The query should describe what information you
        are looking for in natural language. If you are unsure which namespace to
        search, call list_namespaces first rather than guessing.

        Args:
            query: Natural language description of the information needed.
            namespace: Document scope to search within (e.g., "legal", "kyc_aml").
            top_k: Number of chunks to retrieve (1 to 20, default 5).
            mode: Retrieval strategy: "hybrid" (default, best quality), "vector_only", or "bm25_only".

        Returns:
            JSON string containing the retrieved chunks with content, scores, and metadata.
        """
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
                return json.dumps({"result": "No relevant chunks found", "count": 0})

            results = []
            for i, c in enumerate(chunks):
                score = (
                    c.get("rrf_score") or
                    c.get("vector_score") or
                    c.get("bm25_score") or 0.0
                )
                content = c["content"]
                results.append({
                    "chunk_index": i,
                    "document_id": c["document_id"],
                    "source_filename": c.get("source_filename", "unknown"),
                    "score": round(float(score), 4),
                    "content": content[:500],
                    "truncated": len(content) > 500,
                })

            return json.dumps({"count": len(results), "chunks": results}, indent=2)

        except Exception as e:
            logger.error("[agent/retrieve] error: %s", e)
            return json.dumps({"error": str(e)})

    return retrieve_chunks

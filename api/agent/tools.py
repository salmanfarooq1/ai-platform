import json
import logging
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from api.auth import KB_NOT_FOUND_MESSAGE
from api.services.embedding import embed_query
from api.services.retriever import RetrieverConfig, retrieve
from config import FEATURES, LLM_CONFIG
from gateway import Action, ActionKind, EnforcementContext, enforce
from gateway.estimate import estimate_tokens
from ports import Adapters

logger = logging.getLogger("api.agent.tools")


def gateway_from_config(config: RunnableConfig | None) -> EnforcementContext | None:
    """The request's enforcement context, put in `configurable` by the route.

    The model cannot set it: it is not a tool argument. Missing means the tools refuse to run (fail
    closed). The tools see the boundary through it, never the raw principal.
    """
    ctx = (config or {}).get("configurable", {}).get("gateway")
    return ctx if isinstance(ctx, EnforcementContext) and ctx.boundary.tenant_id is not None else None


_NO_TENANT = json.dumps({"error": "unauthenticated", "reason": "No tenant is bound to this agent run"})


async def _gate(ctx: EnforcementContext, action: Action, halt: bool) -> str | None:
    """Run `enforce()`. On a deny returns the JSON the model sees, and (for tool calls) ends the agent loop."""
    decision = await enforce(ctx, action)
    if decision.allowed:
        return None
    if halt:
        ctx.halted = decision.reason
    return json.dumps({"error": "policy_denied", "reason": decision.reason})


def make_list_namespaces_tool(adapters: Adapters):
    """Build the list_namespaces tool: it reads the calling tenant's knowledge bases."""

    @tool
    async def list_namespaces(config: RunnableConfig) -> str:
        """
        List the document namespaces (knowledge bases) available to search, with a short
        description of what each one contains.

        Call this if you are unsure which namespace fits the question, instead
        of guessing (namespaces change over time as new document sets are
        added, so do not assume the ones you have seen before are the full list).

        Returns:
            JSON string mapping namespace name to a description.
        """
        ctx = gateway_from_config(config)
        if ctx is None or ctx.boundary.tenant_id is None:
            return _NO_TENANT
        denied = await _gate(ctx, Action(ActionKind.TOOL_CALL, "list_namespaces"), halt=True)
        if denied is not None:
            return denied
        try:
            knowledge_bases = await adapters.knowledge.list_knowledge_bases(ctx.boundary.tenant_id)
            visible = ctx.boundary.visible_kbs()
            return json.dumps({slug: description for slug, description in knowledge_bases.items() if visible is None or slug in visible})
        except Exception as e:
            logger.error("[agent/list_namespaces] error: %s", e)
            return json.dumps({"error": str(e)})

    return list_namespaces


def make_retrieve_tool(adapters: Adapters):
    """
    Build the retrieve_chunks tool bound to the app's ports (knowledge store and embeddings).

    Built as a closure instead of a module-level global flipped on every request so the tool is constructed
    once, at app startup, alongside the graph. Avoids mutable module state shared across concurrent requests,
    and is trivially testable: pass in fake adapters, no monkeypatching a global.
    """

    @tool
    async def retrieve_chunks(
        query: str,
        namespace: str = "default",
        top_k: int = 5,
        mode: Literal["hybrid", "vector_only", "bm25_only"] = "hybrid",
        *,
        config: RunnableConfig,
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
        ctx = gateway_from_config(config)
        if ctx is None or ctx.boundary.tenant_id is None:
            return _NO_TENANT
        tenant_id = ctx.boundary.tenant_id
        denied = await _gate(ctx, Action(ActionKind.TOOL_CALL, "retrieve_chunks", input_text=query), halt=True)
        if denied is None:
            denied = await _gate(ctx, Action(ActionKind.KB_READ, namespace, input_text=query), halt=False)
        if denied is None:
            denied = await _gate(ctx, Action(
                ActionKind.MODEL_INVOKE, LLM_CONFIG["embedding_model"], estimated_tokens=estimate_tokens(query),
                input_text=query,
            ), halt=False)
        if denied is not None:
            return denied
        try:
            # Same check and same answer as the REST routes and MCP: a namespace that is not one of the
            # tenant's knowledge bases is "not found", whether it is missing or another tenant's.
            if not await adapters.knowledge.kb_exists(tenant_id, namespace):
                return json.dumps({"error": "kb_not_found", "reason": KB_NOT_FOUND_MESSAGE})
            k = max(1, min(top_k, 20))
            query_embedding = await embed_query(adapters.embeddings, query)

            cfg = RetrieverConfig(
                top_k=k,
                mode=mode,
                rerank=FEATURES.get("reranker_enabled", False),
            )

            chunks = await retrieve(
                store=adapters.knowledge,
                query=query,
                query_embedding=query_embedding,
                namespace=namespace,
                cfg=cfg,
                tenant_id=tenant_id,
            )

            if not chunks:
                return json.dumps({"result": "No relevant chunks found", "count": 0})

            results = []
            for i, c in enumerate(chunks):
                if "rrf_score" in c and c["rrf_score"] is not None:
                    score = c["rrf_score"]
                elif "vector_score" in c and c["vector_score"] is not None:
                    score = c["vector_score"]
                else:
                    score = c.get("bm25_score", 0.0)

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

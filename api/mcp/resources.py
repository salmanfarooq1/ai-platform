"""
MCP resource definitions.

Resources expose read-only platform data to MCP clients.
Unlike tools, resources are passive — the client reads them like a file
rather than invoking them like a function.
"""
import json
import logging
from typing import Any

from asyncpg import Pool

from api.mcp.server import mcp
from config import FEATURES, NAMESPACE_REGISTRY

logger = logging.getLogger("api.mcp.resources")


@mcp.resource("rag://config/namespaces")
async def resource_namespaces() -> str:
    """Current namespace registry with descriptions."""
    return json.dumps(NAMESPACE_REGISTRY, indent=2)


@mcp.resource("rag://config/features")
async def resource_features() -> str:
    """Active feature flags for this deployment."""
    return json.dumps(FEATURES, indent=2)


@mcp.resource("rag://documents/{namespace}/{document_id}")
async def resource_document(namespace: str, document_id: str) -> str:
    """Full chunk listing for a specific ingested document."""
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata
                FROM documents
                WHERE namespace = $1 AND document_id = $2
                ORDER BY id
                """,
                namespace, document_id,
            )

        chunks = [
            {"chunk_id": r["id"], "content": r["content"], "metadata": dict(r["metadata"] or {})}
            for r in rows
        ]
        return json.dumps({"document_id": document_id, "namespace": namespace, "chunks": chunks}, indent=2)

    except Exception as e:
        logger.error("[mcp/resource_document] %s", e)
        return json.dumps({"error": str(e)})

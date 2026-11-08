"""
MCP resource definitions.

Resources expose read-only platform data to MCP clients.
Unlike tools, resources are passive — the client reads them like a file
rather than invoking them like a function.
"""
import json
import logging

from api.mcp.context import gate, scope_denied, session_adapters, session_pool, session_tenant
from api.mcp.server import mcp
from config import FEATURES
from core.database.tenant import tenant_connection
from core.identity.models import Scope
from gateway import Action, ActionKind

logger = logging.getLogger(__name__)


@mcp.resource("rag://config/namespaces")
async def resource_namespaces() -> str:
    """The caller's knowledge bases with descriptions."""
    tenant_id, pool, adapters = session_tenant(), session_pool(), session_adapters()
    if tenant_id is None:
        return json.dumps({"error": "unauthenticated"})
    if (denied := scope_denied(Scope.KB_READ)) is not None:
        return denied
    if pool is None or adapters is None:
        return json.dumps({"error": "Database pool not available"})
    ctx = await gate(Action(ActionKind.TOOL_CALL, "resource_namespaces"), Action(ActionKind.KB_READ))
    visible = ctx.boundary.visible_kbs()
    try:
        knowledge_bases = await adapters.knowledge.list_knowledge_bases(tenant_id)
        return json.dumps({slug: description for slug, description in knowledge_bases.items() if visible is None or slug in visible}, indent=2)
    except Exception as exc:
        logger.warning("MCP resource %s failed with %s", "resource_namespaces", type(exc).__name__)
        raise RuntimeError("MCP operation failed") from None


@mcp.resource("rag://config/features")
async def resource_features() -> str:
    """Active feature flags for this deployment."""
    if session_tenant() is None:
        return json.dumps({"error": "unauthenticated"})
    if session_pool() is None:
        return json.dumps({"error": "Database pool not available"})
    await gate(Action(ActionKind.TOOL_CALL, "resource_features"))
    return json.dumps(FEATURES, indent=2)


@mcp.resource("rag://documents/{namespace}/{document_id}")
async def resource_document(namespace: str, document_id: str) -> str:
    """Full chunk listing for a specific ingested document."""
    tenant_id, pool = session_tenant(), session_pool()
    if tenant_id is None:
        return json.dumps({"error": "unauthenticated"})
    if (denied := scope_denied(Scope.KB_READ)) is not None:
        return denied
    if pool is None:
        return json.dumps({"error": "Database pool not available"})
    await gate(Action(ActionKind.TOOL_CALL, "resource_document"), Action(ActionKind.KB_READ, namespace))

    try:
        async with tenant_connection(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata
                FROM documents
                WHERE tenant_id = $3 AND namespace = $1 AND document_id = $2
                ORDER BY id
                """,
                namespace, document_id, tenant_id,
            )

        chunks = [
            {"chunk_id": r["id"], "content": r["content"], "metadata": dict(r["metadata"] or {})}
            for r in rows
        ]
        return json.dumps({"document_id": document_id, "namespace": namespace, "chunks": chunks}, indent=2)

    except Exception as exc:
        logger.warning("MCP resource %s failed with %s", "resource_document", type(exc).__name__)
        raise RuntimeError("MCP operation failed") from None

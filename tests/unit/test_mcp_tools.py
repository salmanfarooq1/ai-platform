"""Unit tests for MCP server tools."""
import json

import pytest

from api.mcp.server import mcp


@pytest.fixture(autouse=True)
def reset_mcp_dependencies():
    """Ensure every test starts with a clean slate for mcp context overrides."""
    old = mcp._dependency_overrides.copy()
    yield
    mcp._dependency_overrides = old


def test_mcp_server_has_name():
    assert mcp.name == "RAG-Platform"


@pytest.mark.asyncio
async def test_list_namespaces_tool():
    from api.mcp.tools import list_namespaces
    result = await list_namespaces()
    data = json.loads(result)
    assert "legal" in data
    assert "kyc_aml" in data
    assert "default" in data


@pytest.mark.asyncio
async def test_search_documents_missing_pool():
    """Without a DB pool in context, tools return a clean JSON error."""
    from api.mcp.tools import search_documents
    mcp._dependency_overrides.pop("app_context", None)
    result = await search_documents(query="test", namespace="default")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_search_documents_blocked_query():
    """Input guardrails apply to MCP tools, not just HTTP routes."""
    from api.mcp.tools import search_documents
    long_query = "x" * 2000
    result = await search_documents(query=long_query, namespace="default")
    data = json.loads(result)
    assert data.get("error") == "query_blocked"


@pytest.mark.asyncio
async def test_get_ingestion_status_missing_pool():
    from api.mcp.tools import get_ingestion_status
    mcp._dependency_overrides.pop("app_context", None)
    result = await get_ingestion_status(namespace="default")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_get_cost_summary_clamps_days():
    from api.mcp.tools import get_cost_summary
    mcp._dependency_overrides["app_context"] = {"pool": None}
    result = await get_cost_summary(days=100)
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_multi_namespace_defaults_to_all():
    """multi_namespace_search with no explicit list should use all known namespaces."""
    from unittest.mock import patch, AsyncMock
    from config import NAMESPACE_REGISTRY
    import json
    
    with patch("api.mcp.tools.search_documents", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = json.dumps({"count": 0, "chunks": []})
        
        from api.mcp.tools import multi_namespace_search
        await multi_namespace_search(query="test")
        
        assert mock_search.call_count == len(NAMESPACE_REGISTRY)
        
        # Verify it passed each namespace exactly once
        called_namespaces = [call.kwargs.get("namespace") for call in mock_search.mock_calls]
        for ns in NAMESPACE_REGISTRY:
            assert ns in called_namespaces

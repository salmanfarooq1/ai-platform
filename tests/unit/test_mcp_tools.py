"""Unit tests for MCP server tools."""
import json
from uuid import UUID, uuid4

import pytest

from api.mcp.context import current_principal
from api.mcp.server import mcp
from core.identity.models import Principal
from tests.fakes import FakePool


@pytest.fixture(autouse=True)
def reset_mcp_dependencies():
    """Ensure every test starts with a clean slate for mcp context overrides."""
    old = mcp._dependency_overrides.copy()
    yield
    mcp._dependency_overrides = old


TENANT = UUID("00000000-0000-0000-0000-0000000000aa")


@pytest.fixture
def principal():
    """Bind a principal the way SseApp does from the verified credential."""
    token = current_principal.set(Principal(id=uuid4(), tenant_id=TENANT, kind="service", scopes=frozenset({"query", "kb:read"})))
    yield
    current_principal.reset(token)


def test_mcp_server_has_name():
    assert mcp.name == "RAG-Platform"


@pytest.mark.asyncio
async def test_list_namespaces_tool(principal):
    from api.mcp.tools import list_namespaces
    pool = FakePool(rows=[{"slug": "default", "description": "d"}, {"slug": "kyc_aml", "description": "k"},
                          {"slug": "legal", "description": "l"}])
    mcp._dependency_overrides["app_context"] = {"pool": pool}
    result = await list_namespaces()
    data = json.loads(result)
    assert data == {"default": "d", "kyc_aml": "k", "legal": "l"}
    assert pool.conn.queries[0] == ("SELECT set_config('app.tenant_id', $1, true)", (str(TENANT),))


@pytest.mark.asyncio
async def test_every_tool_refuses_without_a_principal():
    """No principal bound to the session (no verified credential) means no data and no tenant guess."""
    from api.mcp.tools import (
        get_cost_summary,
        get_ingestion_status,
        list_namespaces,
        multi_namespace_search,
        search_documents,
    )
    mcp._dependency_overrides["app_context"] = {"pool": FakePool()}
    for call in (list_namespaces(), search_documents(query="q", namespace="legal"), multi_namespace_search(query="q"),
                 get_ingestion_status(namespace="legal"), get_cost_summary(days=1)):
        assert json.loads(await call)["error"] == "unauthenticated"


@pytest.mark.asyncio
async def test_search_documents_missing_pool(principal):
    """Without a DB pool in context, tools return a clean JSON error."""
    from api.mcp.tools import search_documents
    mcp._dependency_overrides.pop("app_context", None)
    result = await search_documents(query="test", namespace="default")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_search_documents_blocked_query(principal):
    """Input guardrails apply to MCP tools, not just HTTP routes (now a gateway stage, so a principal is needed)."""
    from api.mcp.tools import search_documents
    mcp._dependency_overrides["app_context"] = {"pool": FakePool()}
    long_query = "x" * 2000
    result = await search_documents(query=long_query, namespace="default")
    data = json.loads(result)
    assert data.get("error") == "query_blocked"


@pytest.mark.asyncio
async def test_get_ingestion_status_missing_pool(principal):
    from api.mcp.tools import get_ingestion_status
    mcp._dependency_overrides.pop("app_context", None)
    result = await get_ingestion_status(namespace="default")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_get_cost_summary_clamps_days(principal):
    from api.mcp.tools import get_cost_summary
    mcp._dependency_overrides["app_context"] = {"pool": None}
    result = await get_cost_summary(days=100)
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_multi_namespace_defaults_to_all_of_the_tenants_knowledge_bases(principal):
    """multi_namespace_search with no explicit list should use every knowledge base the tenant owns."""
    import json
    from unittest.mock import AsyncMock, patch

    mcp._dependency_overrides["app_context"] = {"pool": FakePool(rows=[
        {"slug": "legal", "description": "l"}, {"slug": "acme_policies", "description": "p"},
    ])}

    with patch("api.mcp.tools.search_documents", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = json.dumps({"count": 0, "chunks": []})

        from api.mcp.tools import multi_namespace_search
        await multi_namespace_search(query="test")

        assert mock_search.call_count == 2

        # Verify it passed each namespace exactly once
        called_namespaces = [call.kwargs.get("namespace") for call in mock_search.mock_calls]
        assert sorted(called_namespaces) == ["acme_policies", "legal"]


def _bind(*scopes):
    return current_principal.set(Principal(id=uuid4(), tenant_id=TENANT, kind="service", scopes=frozenset(scopes)))


@pytest.mark.asyncio
async def test_each_mcp_tool_demands_the_scope_of_its_rest_twin():
    """search -> query; ingestion status, cost summary, namespaces -> kb:read (as /v1/documents, /v1/analytics)."""
    from api.mcp.tools import (
        get_cost_summary,
        get_ingestion_status,
        list_namespaces,
        multi_namespace_search,
        search_documents,
    )

    mcp._dependency_overrides["app_context"] = {"pool": FakePool()}
    calls = {
        "query": [search_documents(query="q", namespace="legal"), multi_namespace_search(query="q", namespaces=["legal"])],
        "kb:read": [list_namespaces(), get_ingestion_status(namespace="legal"), get_cost_summary(days=1)],
    }
    other = {"query": "kb:read", "kb:read": "query"}
    for needed, coros in calls.items():
        for coro in coros:
            token = _bind(other[needed])  # holds only the OTHER scope
            try:
                data = json.loads(await coro)
            finally:
                current_principal.reset(token)
            assert data == {"error": "forbidden", "reason": f"Missing required scope: {needed}"}


@pytest.mark.asyncio
async def test_mcp_tools_pass_the_scope_check_with_the_right_scope_or_admin():
    from api.mcp.tools import get_cost_summary, list_namespaces

    mcp._dependency_overrides["app_context"] = {"pool": FakePool(rows=[])}
    for scopes in (("kb:read",), ("admin",)):
        token = _bind(*scopes)
        try:
            assert json.loads(await list_namespaces()) == {}
            assert json.loads(await get_cost_summary(days=1))["days"] == 1
        finally:
            current_principal.reset(token)


@pytest.mark.asyncio
async def test_mcp_resources_demand_kb_read():
    from api.mcp.resources import resource_document, resource_namespaces

    mcp._dependency_overrides["app_context"] = {"pool": FakePool()}
    token = _bind("query")
    try:
        for coro in (resource_namespaces(), resource_document("legal", "gdpr.md")):
            assert json.loads(await coro) == {"error": "forbidden", "reason": "Missing required scope: kb:read"}
    finally:
        current_principal.reset(token)

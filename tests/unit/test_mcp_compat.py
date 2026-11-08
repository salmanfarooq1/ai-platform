"""Expected denials keep their reason; unexpected errors reach neither peers nor logs."""
import importlib.util
import os
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import CallToolRequestParams, ReadResourceRequestParams

from gateway import GatewayDenied
from gateway.types import Decision

pytestmark = pytest.mark.unit


def server_type():
    if before := os.environ.get("MCP_COMPAT_SOURCE"):
        spec = importlib.util.spec_from_file_location("compat_before", Path(before))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.PlatformMCPServer
    from api.mcp.server import PlatformMCPServer
    return PlatformMCPServer


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tool", "resource"])
async def test_expected_gateway_denial_exposes_only_catalogued_reason(kind):
    server = server_type()("compatibility")

    async def denied() -> str:
        raise GatewayDenied(Decision(False, "policy", "kb_not_allowed", message="private policy detail"))

    if kind == "tool":
        server.tool()(denied)
        with pytest.raises(ToolError, match="^Error executing tool denied: kb_not_allowed$"):
            await server.call_tool("denied", {})
    else:
        server.resource("test://denied")(denied)
        with pytest.raises(ResourceError, match="^kb_not_allowed$"):
            await server.read_resource("test://denied")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tool", "resource"])
async def test_unexpected_exception_is_masked_in_response_and_application_logs(kind, caplog):
    server = server_type()("compatibility")
    sentinel = "SENTINEL_PRIVATE_EXCEPTION_VALUE"

    async def failing() -> str:
        raise RuntimeError(sentinel)

    if kind == "tool":
        server.tool()(failing)
        result = await server._handle_call_tool(None, CallToolRequestParams(name="failing", arguments={}))
        assert result.is_error
        response = result.model_dump_json()
    else:
        from mcp import MCPError
        server.resource("test://failing")(failing)
        with pytest.raises(MCPError) as caught:
            await server._handle_read_resource(None, ReadResourceRequestParams(uri="test://failing"))
        response = str(caught.value)
    assert sentinel not in response
    assert sentinel not in caplog.text
    assert "unexpected exception" in caplog.text


@pytest.mark.asyncio
async def test_registered_tool_does_not_log_private_provider_failure(monkeypatch, caplog):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    if before := os.environ.get("MCP_COMPAT_SOURCE"):
        import api.mcp.server as module
        mcp = server_type()("compatibility")
        monkeypatch.setattr(module, "mcp", mcp)
        spec = importlib.util.spec_from_file_location("tools_before", Path(before).with_name("tools.py"))
        tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tools)
    else:
        from api.mcp import tools
        from api.mcp.server import mcp

    sentinel = "SENTINEL_PRIVATE_PROVIDER_VALUE"
    monkeypatch.setattr(tools, "session_tenant", uuid4)
    monkeypatch.setattr(tools, "scope_denied", lambda scope: None)
    monkeypatch.setattr(tools, "session_pool", lambda: object())
    knowledge = SimpleNamespace(list_knowledge_bases=AsyncMock(side_effect=RuntimeError(sentinel)))
    monkeypatch.setattr(tools, "session_adapters", lambda: SimpleNamespace(knowledge=knowledge))
    monkeypatch.setattr(tools, "gate", AsyncMock(return_value=SimpleNamespace(
        boundary=SimpleNamespace(visible_kbs=lambda: None))))
    result = await mcp._handle_call_tool(None, CallToolRequestParams(name="list_namespaces", arguments={}))
    assert result.is_error
    assert sentinel not in result.model_dump_json()
    assert sentinel not in caplog.text
    assert "list_namespaces" in caplog.text and "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_registered_resource_logs_only_resource_name_and_exception_type(monkeypatch, caplog):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from api.mcp import resources

    sentinel = "SENTINEL_PRIVATE_RESOURCE_VALUE"
    monkeypatch.setattr(resources, "session_tenant", uuid4)
    monkeypatch.setattr(resources, "scope_denied", lambda scope: None)
    monkeypatch.setattr(resources, "session_pool", lambda: object())
    knowledge = SimpleNamespace(list_knowledge_bases=AsyncMock(side_effect=RuntimeError(sentinel)))
    monkeypatch.setattr(resources, "session_adapters", lambda: SimpleNamespace(knowledge=knowledge))
    monkeypatch.setattr(resources, "gate", AsyncMock(return_value=SimpleNamespace(
        boundary=SimpleNamespace(visible_kbs=lambda: None))))
    with pytest.raises(RuntimeError, match="MCP operation failed"):
        await resources.resource_namespaces()
    assert sentinel not in caplog.text
    assert "resource_namespaces" in caplog.text and "RuntimeError" in caplog.text

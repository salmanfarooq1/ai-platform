"""Structure check: every agent tool, MCP tool and MCP resource calls the gateway, and only the model seam imports a provider."""
import ast
import textwrap

import pytest

from tests.gate_lint import MCP_FILES, ROOT, agent_tools, governed_functions, mcp_endpoints
from tests.import_lint import GUARDED_FILES, PROVIDER_SEAM

AGENT_TOOLS = {"list_namespaces", "retrieve_chunks"}
MCP_TOOLS = {"list_namespaces", "search_documents", "multi_namespace_search", "get_ingestion_status", "get_cost_summary"}
MCP_RESOURCES = {"resource_namespaces", "resource_features", "resource_document"}


def test_the_lint_finds_every_agent_tool_and_every_one_calls_the_gate():
    found = agent_tools()
    assert set(found) == AGENT_TOOLS
    assert [name for name, gated in found.items() if not gated] == []


def test_the_lint_finds_every_mcp_tool_and_resource_and_every_one_calls_the_gate():
    found: dict[str, bool] = {}
    for path in MCP_FILES:
        found.update(mcp_endpoints(path))
    assert set(found) == MCP_TOOLS | MCP_RESOURCES
    assert [name for name, gated in found.items() if not gated] == []


def test_the_registered_mcp_tools_match_the_ones_the_lint_checked():
    """The lint must not miss a tool: what the server registers is what the AST found."""
    import api.mcp.resources  # noqa: F401 - registers the resources
    import api.mcp.tools  # noqa: F401 - registers the tools
    from api.mcp.server import mcp

    registered = set(mcp._tool_manager._tools)
    assert registered == MCP_TOOLS


_UNGATED_MCP_TOOL = '''
@mcp.tool()
async def sneaky(query: str) -> str:
    return await read_everything(query)
'''
_GATED_MCP_TOOL = '''
@mcp.tool()
async def fine(query: str) -> str:
    await gate(Action(ActionKind.TOOL_CALL, "fine"))
    return await read_everything(query)
'''


@pytest.mark.parametrize("source, decorators, name", [
    (_UNGATED_MCP_TOOL, frozenset({"mcp.tool", "mcp.resource"}), "sneaky"),
    ('@mcp.resource("rag://x")\nasync def r() -> str:\n    return "data"\n', frozenset({"mcp.tool", "mcp.resource"}), "r"),
    ("@tool\nasync def t(query: str) -> str:\n    return query\n", frozenset({"tool"}), "t"),
    # a nested tool inside a factory, as the agent tools are built
    ("def make():\n    @tool\n    async def t(query: str) -> str:\n        return query\n    return t\n", frozenset({"tool"}), "t"),
    # a function that only mentions the gate in a comment, a string or an unrelated name does not count
    ('@mcp.tool()\nasync def s() -> str:\n    # await gate(x)\n    return "gate(x)"\n', frozenset({"mcp.tool"}), "s"),
    ("@mcp.tool()\nasync def s() -> str:\n    gated = 1\n    return str(gated)\n", frozenset({"mcp.tool"}), "s"),
])
def test_a_synthetic_source_without_the_gate_call_fails_the_check(source, decorators, name):
    assert governed_functions(textwrap.dedent(source), decorators) == {name: False}


@pytest.mark.parametrize("source, decorators, name", [
    (_GATED_MCP_TOOL, frozenset({"mcp.tool"}), "fine"),
    ("@tool\nasync def t(config) -> str:\n    return await _gate(ctx, action, halt=True) or ''\n", frozenset({"tool"}), "t"),
    ("@tool\nasync def t(config) -> str:\n    await enforce(ctx, action)\n    return ''\n", frozenset({"tool"}), "t"),
    ("@mcp.resource('rag://x')\nasync def r() -> str:\n    await require(ctx, action)\n    return ''\n", frozenset({"mcp.resource"}), "r"),
])
def test_a_synthetic_source_with_the_gate_call_passes_the_check(source, decorators, name):
    assert governed_functions(textwrap.dedent(source), decorators) == {name: True}


def test_undecorated_helpers_are_not_checked():
    assert governed_functions("async def helper():\n    return 1\n", frozenset({"tool", "mcp.tool"})) == {}


def test_the_real_agent_tools_file_with_the_gate_calls_removed_fails_the_check(tmp_path):
    source = (ROOT / "api" / "agent" / "tools.py").read_text()
    stripped = source.replace("_gate(", "_noop(").replace("enforce(", "_noop(")
    tampered = tmp_path / "tools.py"
    tampered.write_text(stripped)
    assert set(agent_tools(tampered)) == AGENT_TOOLS
    assert not any(agent_tools(tampered).values())


def test_the_real_mcp_tools_file_with_the_gate_calls_removed_fails_the_check(tmp_path):
    tampered = tmp_path / "tools.py"
    tampered.write_text((ROOT / "api" / "mcp" / "tools.py").read_text().replace("gate(", "_noop("))
    assert not any(mcp_endpoints(tampered).values())


def test_the_agent_graph_is_in_the_import_guard():
    names = {p.relative_to(ROOT).as_posix() for p in GUARDED_FILES}
    assert "api/agent/graph.py" in names


def _providers_imported(path) -> list[str]:
    hits = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names if a.name.split(".")[0] in ("litellm", "langchain_litellm")]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in ("litellm", "langchain_litellm"):
            hits.append(node.module)
    return hits


def test_the_model_seam_is_the_only_agent_or_mcp_module_that_imports_a_provider():
    importers = {
        p.relative_to(ROOT).as_posix()
        for folder in ("agent", "mcp")
        for p in sorted((ROOT / "api" / folder).glob("*.py"))
        if _providers_imported(p)
    }
    assert importers == {PROVIDER_SEAM.relative_to(ROOT).as_posix()} == {"api/agent/models.py"}
    assert "litellm" in _providers_imported(PROVIDER_SEAM) and "langchain_litellm" in _providers_imported(PROVIDER_SEAM)

"""Structural lint for the gateway rule: every agent tool, MCP tool and MCP resource must call the gate.

An agent tool is a function decorated with `@tool`. An MCP tool or resource is decorated with `@mcp.tool(...)` or
`@mcp.resource(...)`. The gate is `gate(...)` (MCP), `_gate(...)` (agent tools), `enforce(...)` or `require(...)`.
The check is by AST, so it needs no running app and a new tool without the call fails it.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE_CALLS = frozenset({"gate", "_gate", "enforce", "require"})
AGENT_TOOLS_FILE = ROOT / "api" / "agent" / "tools.py"
MCP_FILES = [ROOT / "api" / "mcp" / "tools.py", ROOT / "api" / "mcp" / "resources.py"]

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _decorator_name(node: ast.expr) -> str:
    """`tool`, `mcp.tool` or `mcp.resource` for `@tool`, `@mcp.tool()` and `@mcp.resource("uri")`."""
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        return f"{target.value.id}.{target.attr}"
    return target.id if isinstance(target, ast.Name) else ""


def _called_names(func: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            f = node.func
            names.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return names


def governed_functions(source: str, decorators: frozenset[str]) -> dict[str, bool]:
    """name -> whether its body calls the gate, for every function carrying one of `decorators`."""
    found: dict[str, bool] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, _FUNCTIONS) and any(_decorator_name(d) in decorators for d in node.decorator_list):
            found[node.name] = bool(_called_names(node) & GATE_CALLS)
    return found


def agent_tools(path: Path = AGENT_TOOLS_FILE) -> dict[str, bool]:
    return governed_functions(path.read_text(encoding="utf-8"), frozenset({"tool"}))


def mcp_endpoints(path: Path) -> dict[str, bool]:
    return governed_functions(path.read_text(encoding="utf-8"), frozenset({"mcp.tool", "mcp.resource"}))

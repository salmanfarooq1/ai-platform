"""Agent and MCP packages depend on the gateway's public API only."""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_agent_and_mcp_import_only_the_gateway_package():
    root = Path(__file__).resolve().parents[2]
    source_roots = (root / "api/agent", root / "api/mcp", root / "sandbox_agent")
    violations = []
    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("gateway."):
                    violations.append(f"{path.relative_to(root)}:{node.lineno}: from {node.module} import")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("gateway."):
                            violations.append(f"{path.relative_to(root)}:{node.lineno}: import {alias.name}")
    assert violations == []

"""Showcase code consumes the same public product seams as an operator."""
import ast
from pathlib import Path

import pytest

PRODUCT_PACKAGES = {"api", "gateway", "core", "adapters", "ports", "workers", "evidence", "sandbox_agent"}
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("path", sorted((ROOT / "scripts/showcase").rglob("*.py")), ids=lambda path: path.name)
def test_showcase_imports_no_product_private_names(path):
    tree = ast.parse(path.read_text())
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in PRODUCT_PACKAGES:
            violations.extend(alias.name for alias in node.names if alias.name.startswith("_") or alias.name == "*")
            violations.extend(part for part in node.module.split(".") if part.startswith("_"))
        elif isinstance(node, ast.Import):
            violations.extend(alias.name for alias in node.names
                              if alias.name.split(".")[0] in PRODUCT_PACKAGES
                              and any(part.startswith("_") for part in alias.name.split(".")))
    assert not violations, f"{path.name} imports private product names: {violations}"


def test_restore_delegates_cas_to_public_product_api(monkeypatch):
    from unittest.mock import Mock

    from scripts.showcase import policy_restore

    publish = Mock(return_value=8)
    monkeypatch.setattr(policy_restore, "set_policy", publish)
    conn = object()  # The wrapper must not open a cursor or issue SQL itself.
    assert policy_restore.restore_policy(conn, "tenant", 7, {}) == 8
    publish.assert_called_once_with(conn, "tenant", {}, "showcase-restore", expected_version=7)


DATABASE_PACKAGES = {"psycopg", "psycopg2", "sqlalchemy", "asyncpg"}


def product_sql(source):
    import re

    pattern = re.compile(
        r"\b(?:SELECT\b[\s\S]*?\bFROM|INSERT\s+INTO|UPDATE\b[\s\S]*?\bSET|"
        r"DELETE\s+FROM|LOCK\s+TABLE|TRUNCATE|ALTER|CREATE|DROP)\b", re.IGNORECASE,
    )
    violations = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and pattern.search(node.value):
            violations.append(node.lineno)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in {"execute", "executemany", "copy"}):
            violations.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in DATABASE_PACKAGES:
            violations.append(node.lineno)
        elif isinstance(node, ast.Import) and any(alias.name.split(".")[0] in DATABASE_PACKAGES for alias in node.names):
            violations.append(node.lineno)
    return violations


@pytest.mark.parametrize("path", sorted((ROOT / "scripts/showcase").rglob("*.py")), ids=lambda path: path.name)
def test_showcase_contains_no_product_sql(path):
    assert not product_sql(path.read_text()), f"{path.name} contains SQL, database imports or database method calls"


@pytest.mark.parametrize("statement", [
    "SELECT id FROM gateway_decisions", "select * from public.api_keys",
    "SELECT * FROM tenants JOIN principals ON true", "UPDATE knowledge_bases SET slug = 'x'",
    "INSERT INTO policies VALUES (1)", "LOCK TABLE documents IN SHARE MODE",
])
def test_sql_guard_recognizes_direct_queries_and_cursor_calls(statement):
    assert product_sql(f"cursor.execute({statement!r})")


@pytest.mark.parametrize("statement", [
    "SELECT id FROM arbitrary_rows", "INSERT INTO arbitrary_rows VALUES (1)",
    "UPDATE arbitrary_rows SET value = 2", "DELETE FROM arbitrary_rows",
    "LOCK TABLE arbitrary_rows", "TRUNCATE arbitrary_rows", "ALTER\nTABLE arbitrary_rows ADD x int",
    "CREATE VIEW arbitrary_view AS SELECT 1", "DROP VIEW arbitrary_view",
    "sElEcT x\nFrOm arbitrary_rows",
])
def test_sql_guard_recognizes_any_table(statement):
    assert product_sql(f"query = {statement!r}")


@pytest.mark.parametrize("method", ["execute", "executemany", "copy"])
def test_sql_guard_rejects_calls_without_literal_sql(method):
    assert product_sql(f"connection.{method}(query)")


@pytest.mark.parametrize("module", ["psycopg", "psycopg2", "sqlalchemy", "asyncpg"])
@pytest.mark.parametrize("style", ["import", "from"])
def test_sql_guard_rejects_database_imports(module, style):
    source = f"import {module}.extras as db" if style == "import" else f"from {module} import connect"
    assert product_sql(source)


def test_server_entrypoint_has_no_adapter_construction():
    tree = ast.parse((ROOT / "scripts/showcase/m0_server.py").read_text())
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] == "adapters"]


@pytest.mark.parametrize("source", [
    "from core.identity.admin import _as_tenant",
    "from gateway import *", "from core._private import value", "import core._private as hidden",
])
def test_private_import_guard_rejects_seeded_sources(source):
    from types import SimpleNamespace

    path = SimpleNamespace(name="seed.py", read_text=lambda: source)
    with pytest.raises(AssertionError, match="private product names"):
        test_showcase_imports_no_product_private_names(path)

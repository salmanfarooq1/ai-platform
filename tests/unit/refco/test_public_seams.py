"""Showcase code consumes the same public product seams as an operator."""
import ast
import re
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


# --- WP4: the recovery drill and the M0 helpers use public seams only -----------------------------------------------------

SDK_MODULES = {"openai", "anthropic", "litellm", "ollama", "google", "cohere", "mistralai", "groq", "boto3", "langchain"}
SDK_ENV = re.compile(r"(OPENAI|ANTHROPIC|OLLAMA|LITELLM|GEMINI|AZURE|GROQ|COHERE)[A-Z_]*(BASE|URL|HOST|KEY|ENDPOINT)", re.IGNORECASE)
LIFECYCLE_FORBIDDEN_ROOTS = PRODUCT_PACKAGES | {"scripts", "config", "tests"}


def _env_key(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(SDK_ENV.search(node.value))


STRICT_SQL = re.compile(r"\b(?:SELECT\b[\s\S]*?\bFROM|INSERT\s+INTO|UPDATE\b[\s\S]*?\bSET|DELETE\s+FROM|TRUNCATE\s+\w|"
                        r"(?:ALTER|CREATE|DROP)\s+(?:TABLE|DATABASE|VIEW|INDEX|ROLE|SCHEMA))\b", re.IGNORECASE)


def strict_sql(source):
    """Like `product_sql`, for scripts whose CLI words ("create-key") must not look like SQL: statements, db imports, cursors."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and STRICT_SQL.search(node.value):
            lines.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "executemany", "copy"}:
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in DATABASE_PACKAGES:
            lines.append(node.lineno)
        elif isinstance(node, ast.Import) and any(a.name.split(".")[0] in DATABASE_PACKAGES for a in node.names):
            lines.append(node.lineno)
    return lines


def _root_name(node):
    """`a.b.c` -> "a" (the name at the root of an attribute chain), else None."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _imported_names(tree):
    """The names this file's imports bind, with aliases resolved by the import itself (`import a.b` binds `a`)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {a.asname or a.name for a in node.names if a.name != "*"}
    return names


def python_lifecycle_violations(source, *, product_imports=False):
    """Everything a lifecycle script may not do: import the product or an SDK, run SQL, or override an SDK globally.

    `product_imports=True` is for the journey and its helpers: they legitimately call public product modules (the existing
    private-name guard above forbids their private names), so only SDK imports, SQL and overrides are flagged there."""
    forbidden_roots = SDK_MODULES if product_imports else LIFECYCLE_FORBIDDEN_ROOTS | SDK_MODULES
    found = [f"sql line {line}" for line in strict_sql(source)]
    tree = ast.parse(source)
    sdk_names = set()
    imported = _imported_names(tree)  # every name an import binds in this file, whatever the module
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node
    aliases = set(imported) | sdk_names | {"httpx", "requests", "urllib3", "socket"}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in aliases:
                        aliases.add(target.id)
                        changed = True

    def module_root(node, context):
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        if isinstance(node, ast.Call):
            return ast.unparse(node.func) in {"__import__", "importlib.import_module"} or (
                ast.unparse(node.func) == "vars" and bool(node.args) and module_root(node.args[0], context))
        if not isinstance(node, ast.Name) or node.id not in aliases:
            return False
        parent = context
        while hasattr(parent, "parent"):
            parent = parent.parent
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                args = parent.args
                if node.id in {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)} | {
                    a.arg for a in (args.vararg, args.kwarg) if a
                }:
                    return False
        return True

    def targets(target):
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                yield from targets(item)
        else:
            yield target

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in forbidden_roots:
                found.append(f"import {node.module}")
            if node.module == "unittest" and any(a.name == "mock" for a in node.names) or node.module.startswith("unittest.mock"):
                found.append("mock")
            sdk_names |= {a.asname or a.name for a in node.names} if root in SDK_MODULES else set()
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in forbidden_roots:
                    found.append(f"import {alias.name}")
                if root in SDK_MODULES:
                    sdk_names.add(alias.asname or root)
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete, ast.For, ast.AsyncFor, ast.withitem)):
            raw_targets = (node.targets if isinstance(node, (ast.Assign, ast.Delete)) else
                           [node.optional_vars] if isinstance(node, ast.withitem) else [node.target])
            for target in (item for raw in raw_targets if raw is not None for item in targets(raw)):
                if isinstance(target, (ast.Attribute, ast.Subscript)) and module_root(target, node) and (
                    isinstance(target, ast.Attribute) or isinstance(target.value, ast.Call)
                    or isinstance(target.value, ast.Attribute) and target.value.attr == "__dict__"):
                    found.append(f"global override of {ast.unparse(target)}")
                if isinstance(target, ast.Subscript):
                    holder = ast.unparse(target.value)
                    if holder in {"os.environ", "environ"} and _env_key(target.slice):
                        found.append("sdk environment override")
                    if holder == "sys.modules":
                        found.append("sys.modules override")
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in {"setattr", "object.__setattr__", "os.putenv"} and node.args and (name == "os.putenv" and _env_key(node.args[0])
                                                                  or name in {"setattr", "object.__setattr__"}
                                                                  and module_root(node.args[0], node)):
                found.append(f"{name} override")
            if name in {"os.environ.update", "os.environ.setdefault", "environ.update", "environ.setdefault"}:
                if any(_env_key(arg) for arg in node.args) or any(SDK_ENV.search(kw.arg or "") for kw in node.keywords):
                    found.append("sdk environment override")
            if name.endswith("monkeypatch.setattr") or name.endswith("monkeypatch.setenv") or name.split(".")[-1] == "patch":
                found.append("patching")
    return sorted(set(found))


SHELL_FORBIDDEN = (
    (re.compile(r"\b(psql|pg_dump|pg_restore|pg_dumpall|valkey-cli|redis-cli)\b"), "a database client"),
    (re.compile(r"\bdocker\b"), "docker"),
    (re.compile(r"\b(?:export\s+|env\s+)?" + SDK_ENV.pattern + r"\s*=", re.IGNORECASE), "an SDK environment override"),
    (re.compile(r"\b(sitecustomize|usercustomize|PYTHONSTARTUP|LD_PRELOAD)\b"), "an interpreter hook"),
    (re.compile(r"(?:from|import)\s+(?:core|gateway|api|adapters|workers|evidence|ports|scripts\.poc_lib|scripts\.poc_backup)\b"), "a product import"),
    (re.compile(r"\.env(?:\.local)?\b"), "the developer environment file"),
)


def shell_lifecycle_violations(source):
    stripped = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    found = [label for pattern, label in SHELL_FORBIDDEN if pattern.search(stripped)]
    if re.search(r"\b(?:SELECT\b[\s\S]*?\bFROM|INSERT\s+INTO|UPDATE\b[\s\S]*?\bSET|DELETE\s+FROM|TRUNCATE|DROP\s+(?:TABLE|DATABASE)|ALTER\s+TABLE)\b", stripped, re.IGNORECASE):
        found.append("product SQL")
    return found


@pytest.mark.parametrize("source,expect", [
    ("from core.identity.admin import admin_connection", "import core.identity.admin"),
    ("import gateway.admin", "import gateway.admin"),
    ("from scripts.poc_lib import up", "import scripts.poc_lib"),
    ("from scripts.showcase.m0 import publish_journey_policy", "import scripts.showcase.m0"),
    ("import psycopg2", "sql line 1"),
    ("from sqlalchemy import text", "sql line 1"),
    ("cursor.execute(query)", "sql line 1"),
    ("q = 'SELECT id FROM gateway_decisions'", "sql line 1"),
    ("import openai", "import openai"),
    ("from anthropic import Anthropic", "import anthropic"),
    ("import litellm\nlitellm.api_base = 'http://x'", "global override of litellm.api_base"),
    ("import httpx\nhttpx.post = lambda *a: None", "global override of httpx.post"),
    ("import socket\nsocket.socket = None", "global override of socket.socket"),
    ("import httpx as h\nh.post = lambda *a: None", "global override of h.post"),
    ("import urllib.request\nurllib.request.urlopen = None", "global override of urllib.request.urlopen"),
    ("import urllib.request as ur\nur.urlopen = None", "global override of ur.urlopen"),
    ("from urllib import request\nrequest.urlopen = None", "global override of request.urlopen"),
    ("import json\njson.dumps = None", "global override of json.dumps"),
    ("import json\njson.dumps += 1", "global override of json.dumps"),
    ("import os.path\nos.path.join = None", "global override of os.path.join"),
    ("from scripts.showcase import m0\nm0.publish = None", "global override of m0.publish"),
    ("import httpx as h\nsetattr(h, 'post', f)", "setattr override"),
    ("import urllib.request\nsetattr(urllib.request, 'urlopen', f)", "setattr override"),
    ("import os\nos.environ['OLLAMA_BASE_URL'] = 'http://x'", "sdk environment override"),
    ("import os\nos.environ.update(OPENAI_API_BASE='http://x')", "sdk environment override"),
    ("import os\nos.environ.setdefault('ANTHROPIC_BASE_URL', 'x')", "sdk environment override"),
    ("import os\nos.putenv('LITELLM_BASE_URL', 'x')", "os.putenv override"),
    ("import httpx\nsetattr(httpx, 'get', f)", "setattr override"),
    ("import sys\nsys.modules['openai'] = object()", "sys.modules override"),
    ("from unittest import mock", "mock"),
    ("from unittest.mock import patch", "mock"),
    ("def f(monkeypatch):\n    monkeypatch.setattr(x, 'y', 1)", "patching"),
])
def test_lifecycle_guard_rejects_seeded_python_sources(source, expect):
    assert expect in python_lifecycle_violations(source)


@pytest.mark.parametrize("source,expect", [
    ("psql -c 'select 1'", "a database client"),
    ("pg_dump -Fc rag_platform", "a database client"),
    ("valkey-cli GET cost:x", "a database client"),
    ("docker exec postgres true", "docker"),
    ("docker compose -p x ps", "docker"),
    ("export OLLAMA_BASE_URL=http://x", "an SDK environment override"),
    ("OPENAI_API_BASE=http://x python run.py", "an SDK environment override"),
    ("python -c 'from core.identity.admin import _as_tenant'", "a product import"),
    ("python -c 'import gateway'", "a product import"),
    ("echo 'SELECT id FROM tenants'", "product SQL"),
    ("echo 'DELETE FROM gateway_decisions'", "product SQL"),
    ("cp .env.local x", "the developer environment file"),
    ("PYTHONSTARTUP=x python", "an interpreter hook"),
])
def test_lifecycle_guard_rejects_seeded_shell_sources(source, expect):
    assert expect in shell_lifecycle_violations(source)


def test_lifecycle_guard_accepts_a_clean_source():
    assert python_lifecycle_violations("import json\nimport subprocess\nimport urllib.request\nsubprocess.run(['x'])") == []
    # attributes of local objects are not module attributes
    assert python_lifecycle_violations("import json\nclass A: pass\na = A()\na.x = json.dumps({})\nself_like = a\nself_like.y = 1") == []


@pytest.mark.parametrize("addition", [
    "\nimport httpx as h\nh.post = None\n",
    "\nimport urllib.request\nurllib.request.urlopen = None\n",
    "\nimport json\njson.dumps = None\n",
])
@pytest.mark.parametrize("name", ["scripts/verify/poc_drill.py", "scripts/showcase/m0.py", "scripts/showcase/m0_policy.py", "scripts/showcase/personas.py"])
def test_alias_nested_and_any_module_overrides_go_red_in_every_python_file_class(name, addition):
    text = (ROOT / name).read_text()
    journey = name.startswith("scripts/showcase/")
    assert python_lifecycle_violations(text, product_imports=journey) == []
    assert any(v.startswith("global override of") for v in python_lifecycle_violations(text + addition, product_imports=journey)), (name, addition)
    assert shell_lifecycle_violations("# docker is not used here\npython scripts/poc up demo\n") == []


def test_lifecycle_uses_public_seams():
    """The drill is a shell wrapper around a stdlib-only driver: `poc` commands, public HTTP and the offline verifier."""
    drill_sh = (ROOT / "scripts/verify/poc-drill.sh").read_text()
    drill_py = (ROOT / "scripts/verify/poc_drill.py").read_text()
    assert shell_lifecycle_violations(drill_sh) == [], shell_lifecycle_violations(drill_sh)
    assert python_lifecycle_violations(drill_py) == [], python_lifecycle_violations(drill_py)
    # only public commands: the poc CLI verbs, the public routes, and the offline verifier script
    verbs = set(re.findall(r'"poc",\s*"(\w+)"|_poc\("(\w+)"', drill_py))
    assert {v for pair in verbs for v in pair if v} <= {"up", "backup", "down", "status", "admin", "destroy"}
    routes = set(re.findall(r'"(/v1/[a-z/{}]*)', drill_py))
    assert routes <= {"/v1/config", "/v1/search", "/v1/decisions", "/v1/receipts/", "/v1/receipts/keys", "/v1/usage/summary"}, routes
    assert "scripts/verify/receipt.py" in drill_py and "shell=True" not in drill_py
    # Apply the same strict guard to the journey and its helpers.
    for path in (ROOT / "scripts/showcase").rglob("*.py"):
        assert not python_lifecycle_violations(path.read_text(), product_imports=True), path.name
    path = ROOT / "scripts/showcase/m0.sh"
    assert not shell_lifecycle_violations(path.read_text()), path.name


def test_journey_sources_use_strict_scanner():
    for path in (ROOT / 'scripts/showcase').rglob('*.py'):
        violations = python_lifecycle_violations(path.read_text() + '\nimport httpx\nhttpx.post = None\n', product_imports=True)
        assert 'global override of httpx.post' in violations, path
    path = ROOT / 'scripts/showcase/m0.sh'
    assert shell_lifecycle_violations(path.read_text() + '\npsql -c "select 1"\n')


def test_every_lifecycle_file_class_goes_red_on_a_seeded_violation():
    """One seeded violation per file class: the drill (py, sh), the journey and its helpers (py), and the journey shell."""
    seeded_py = {
        "scripts/verify/poc_drill.py": "\nimport httpx\nhttpx.post = None\n",
        "scripts/showcase/m0.py": "\nimport litellm\nlitellm.api_base = 'http://x'\n",
        "scripts/showcase/m0_policy.py": "\nimport os\nos.environ['OLLAMA_BASE_URL'] = 'http://x'\n",
        "scripts/showcase/personas.py": "\nimport openai\n",
    }
    for name, addition in seeded_py.items():
        text = (ROOT / name).read_text()
        journey = name.startswith("scripts/showcase/")
        assert python_lifecycle_violations(text, product_imports=journey) == [], (name, "the real source is clean")
        assert python_lifecycle_violations(text + addition, product_imports=journey), name
    for name, addition in {"scripts/verify/poc-drill.sh": "\npsql -c 'select 1'\n", "scripts/showcase/m0.sh": "\nexport OPENAI_API_BASE=http://x\n"}.items():
        text = (ROOT / name).read_text()
        assert shell_lifecycle_violations(text) == [], (name, "the real source is clean")
        assert shell_lifecycle_violations(text + addition), name


def test_the_scanner_covers_every_python_and_shell_file_the_journey_and_drill_consist_of():
    covered = {p.name for p in (ROOT / "scripts/showcase").glob("*.py")}
    assert {"m0.py", "m0_policy.py", "personas.py", "policy_restore.py", "m0_server.py"} <= covered
    assert (ROOT / "scripts/showcase/m0.sh").is_file() and (ROOT / "scripts/verify/poc-drill.sh").is_file()


def test_a_private_product_import_in_a_journey_file_goes_red_through_the_private_name_guard():
    from types import SimpleNamespace

    for name in ("m0.py", "m0_policy.py", "personas.py", "policy_restore.py", "m0_server.py"):
        text = (ROOT / "scripts/showcase" / name).read_text() + "\nfrom core.identity.admin import _as_tenant\n"
        with pytest.raises(AssertionError, match="private product names"):
            test_showcase_imports_no_product_private_names(SimpleNamespace(name=name, read_text=lambda text=text: text))
    for name, addition in (("m0.py", "\nq = 'DELETE FROM gateway_decisions'\n"), ("personas.py", "\nconn.execute(q)\n")):
        assert product_sql((ROOT / "scripts/showcase" / name).read_text() + addition), name

@pytest.mark.parametrize("source", [
    "import httpx\nhttpx.post, httpx.get = 1, 2",
    "import httpx\ndel httpx.post",
    "import httpx\nfor httpx.post in []: pass",
    "import httpx\nwith ctx() as httpx.post: pass",
    "import httpx\nx = httpx\nx.post = 1",
    "import sys\nsys.modules['httpx'].post = 1",
    "import importlib\nimportlib.import_module('httpx').post = 1",
    "__import__('httpx').post = 1",
    "import httpx\nobject.__setattr__(httpx, 'post', 1)",
    "import sys\nsetattr(sys.modules['httpx'], 'post', 1)",
    "import httpx\nvars(httpx)['post'] = 1",
    "import httpx\nhttpx.__dict__['post'] = 1",
])
def test_lifecycle_guard_rejects_additional_override_forms(source):
    assert python_lifecycle_violations(source, product_imports=True)


def test_lifecycle_guard_allows_shadowed_module_parameter():
    assert not python_lifecycle_violations('import json\ndef f(json):\n    json.x = 1', product_imports=True)

"""Import lint.

1. The gateway rule: agent tools and MCP code reach providers and the database only through the gateway. They
   must not import `litellm`, `langchain_litellm` or `asyncpg` (at module level, inside a function, or under
   TYPE_CHECKING), nor load them with `importlib.import_module` / `__import__`. Data access goes through the
   ports and `core.database.tenant.tenant_connection`, after `enforce()`.
2. The ports rule (Sprint 006, strict rule 12): provider SDKs live in `adapters/` only. `litellm`,
   `langchain_litellm`, `boto3`/`aioboto3` and `redis` are banned everywhere else in the shipped code, and
   `asyncpg` is allowed only in `adapters/`, `core/database/` and `core/identity/store.py` (identity keeps its own
   store, which runs before any tenant is known and is not a port: see ADR-0005).
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNED = ("litellm", "langchain_litellm", "asyncpg")
GUARDED_FILES = [
    ROOT / "api" / "agent" / "tools.py",
    ROOT / "api" / "agent" / "graph.py",
    *sorted((ROOT / "api" / "mcp").glob("*.py")),
]

# Ports rule: where each banned module may be imported. Everything else is a violation.
PORTS_ROOTS = ("api", "core", "gateway", "ports", "workers")  # directories of shipped code outside adapters/
SDK_ONLY_IN_ADAPTERS = ("litellm", "langchain_litellm", "boto3", "botocore", "aioboto3", "aiobotocore", "redis", "openshell")
ASYNCPG_ALLOWED = ("adapters/", "core/database/", "core/identity/store.py")


def _is_banned(module: str, banned: tuple[str, ...] = BANNED) -> bool:
    return any(module == name or module.startswith(name + ".") for name in banned)


def tree_violations(root: Path = ROOT) -> list[str]:
    """`path:line: what` for every provider or driver import outside the places the ports rule allows."""
    found: list[str] = []
    for top in PORTS_ROOTS:
        for path in sorted((root / top).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            banned = SDK_ONLY_IN_ADAPTERS if rel.startswith(ASYNCPG_ALLOWED) else (*SDK_ONLY_IN_ADAPTERS, "asyncpg")
            found += [f"{rel}:{hit.split(':', 1)[1]}" for hit in banned_imports(path, banned)]
    return found


def banned_imports(path: Path, banned: tuple[str, ...] = BANNED) -> list[str]:
    """`path:line: what` for every banned import in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"{path.name}:{node.lineno}: import {a.name}" for a in node.names if _is_banned(a.name, banned)]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0 and _is_banned(node.module, banned):
            found.append(f"{path.name}:{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in ("import_module", "__import__") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _is_banned(arg.value, banned):
                    found.append(f"{path.name}:{node.lineno}: {name}({arg.value!r})")
    return found

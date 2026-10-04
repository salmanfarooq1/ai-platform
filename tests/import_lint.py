"""Import lint for the gateway rule: agent tools and MCP code reach providers and the database only through
the gateway. They must not import `litellm`, `langchain_litellm` or `asyncpg` (at module level, inside a
function, or under TYPE_CHECKING), nor load them with `importlib.import_module` / `__import__`.

Data access goes through `core.database.tenant.tenant_connection` and the retriever, after `enforce()`.
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
PROVIDER_SEAM = ROOT / "api" / "agent" / "models.py"  # the one agent or MCP module that may import a provider


def _is_banned(module: str) -> bool:
    return any(module == name or module.startswith(name + ".") for name in BANNED)


def banned_imports(path: Path) -> list[str]:
    """`path:line: what` for every banned import in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [f"{path.name}:{node.lineno}: import {a.name}" for a in node.names if _is_banned(a.name)]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0 and _is_banned(node.module):
            found.append(f"{path.name}:{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in ("import_module", "__import__") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _is_banned(arg.value):
                    found.append(f"{path.name}:{node.lineno}: {name}({arg.value!r})")
    return found

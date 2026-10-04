"""Import lint: agent tools and MCP code cannot import litellm, langchain_litellm or asyncpg."""
import textwrap

import pytest

from tests.import_lint import GUARDED_FILES, ROOT, banned_imports


def test_the_guarded_files_exist_and_include_the_agent_tools_and_every_mcp_module():
    names = {p.relative_to(ROOT).as_posix() for p in GUARDED_FILES}
    assert "api/agent/tools.py" in names
    assert {"api/mcp/tools.py", "api/mcp/resources.py", "api/mcp/context.py", "api/mcp/transport.py"} <= names
    assert all(p.exists() for p in GUARDED_FILES)


@pytest.mark.parametrize("path", GUARDED_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_the_current_tree_has_no_banned_imports(path):
    assert banned_imports(path) == []


@pytest.mark.parametrize("source, expected", [
    ("import litellm\n", "import litellm"),
    ("from litellm import acompletion\n", "from litellm import"),
    ("import langchain_litellm\n", "import langchain_litellm"),
    ("from langchain_litellm import ChatLiteLLM\n", "from langchain_litellm import"),
    ("import asyncpg\n", "import asyncpg"),
    ("from asyncpg import Pool\n", "from asyncpg import"),
    ("import litellm.utils\n", "import litellm.utils"),
    ("def tool():\n    import litellm\n    return litellm\n", "import litellm"),  # lazy import inside a function
    ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from asyncpg import Pool\n", "from asyncpg import"),
    ("import importlib\nimportlib.import_module('litellm')\n", "import_module('litellm')"),
    ("__import__('asyncpg')\n", "__import__('asyncpg')"),
])
def test_a_temp_file_with_a_banned_import_is_caught(tmp_path, source, expected):
    bad = tmp_path / "tools.py"
    bad.write_text(source)
    hits = banned_imports(bad)
    assert len(hits) == 1 and expected in hits[0]


def test_the_real_agent_tools_file_plus_one_litellm_import_fails_the_lint(tmp_path):
    """The scenario from the sprint: a litellm import inside tools must fail the check."""
    tampered = tmp_path / "tools.py"
    tampered.write_text((ROOT / "api" / "agent" / "tools.py").read_text() + textwrap.dedent('''

        async def sneaky(prompt):
            import litellm
            return await litellm.acompletion(model="x", messages=[{"role": "user", "content": prompt}])
    '''))
    hits = banned_imports(tampered)
    assert len(hits) == 1 and "import litellm" in hits[0]


@pytest.mark.parametrize("source", [
    "import json\nfrom core.database.tenant import DbPool, tenant_connection\n",
    "# import litellm in a comment\nname = 'litellm'\n",
    "from api.services.llm import generate_with_routing\n",  # going through the service layer is allowed
    "import litellm_proxy_helpers\n",                         # a different package whose name merely starts the same
])
def test_clean_files_are_not_flagged(tmp_path, source):
    ok = tmp_path / "tools.py"
    ok.write_text(source)
    assert banned_imports(ok) == []

"""Import lint for the ports rule: provider SDKs only in adapters/, asyncpg only where the rule allows it."""
import pytest

from tests.import_lint import ROOT, SDK_ONLY_IN_ADAPTERS, tree_violations

pytestmark = pytest.mark.unit


def test_the_current_tree_has_no_violations():
    assert tree_violations() == []


def test_the_adapters_really_hold_the_sdks():
    """The lint is not vacuous: the SDKs are imported, in adapters/."""
    text = {p.name: p.read_text() for p in (ROOT / "adapters").glob("*.py")}
    assert "import litellm" in text["litellm_llm.py"] and "import litellm" in text["litellm_embeddings.py"]
    assert "langchain_litellm" in text["litellm_chat.py"]
    assert "import redis.asyncio" in text["redis_cache.py"]
    assert "import boto3" in text["s3_object_store.py"]
    assert "from core.database.tenant import DbPool" in text["pg_knowledge.py"]


def _tree(tmp_path, relative, source):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    for top in ("api", "core", "gateway", "ports"):
        (tmp_path / top).mkdir(exist_ok=True)
    return tmp_path


@pytest.mark.parametrize("module", SDK_ONLY_IN_ADAPTERS)
@pytest.mark.parametrize("where", ["api/routers/x.py", "core/clients/x.py", "gateway/x.py", "ports/x.py"])
def test_an_sdk_import_outside_adapters_fails_the_lint(tmp_path, module, where):
    root = _tree(tmp_path, where, f"import {module}\n")
    hits = tree_violations(root)
    assert len(hits) == 1 and hits[0].startswith(where) and f"import {module}" in hits[0]


@pytest.mark.parametrize("source, expected", [
    ("from redis.asyncio import Redis\n", "from redis.asyncio import"),
    ("def f():\n    import litellm\n", "import litellm"),
    ("import importlib\nimportlib.import_module('boto3')\n", "import_module('boto3')"),
    ("__import__('aioboto3')\n", "__import__('aioboto3')"),
])
def test_lazy_and_dynamic_imports_are_caught_too(tmp_path, source, expected):
    hits = tree_violations(_tree(tmp_path, "api/x.py", source))
    assert len(hits) == 1 and expected in hits[0]


@pytest.mark.parametrize("module", SDK_ONLY_IN_ADAPTERS)
def test_the_same_import_inside_adapters_is_allowed(tmp_path, module):
    root = _tree(tmp_path, "adapters/x.py", f"import {module}\nimport asyncpg\n")
    assert tree_violations(root) == []  # adapters/ is not even scanned for SDKs


@pytest.mark.parametrize("where", ["api/routers/x.py", "gateway/x.py", "core/ingestion/x.py", "core/identity/admin.py", "ports/x.py"])
def test_asyncpg_outside_the_allowed_places_fails_the_lint(tmp_path, where):
    hits = tree_violations(_tree(tmp_path, where, "from asyncpg import Pool\n"))
    assert len(hits) == 1 and "from asyncpg import" in hits[0]


@pytest.mark.parametrize("where", ["core/database/pool.py", "core/identity/store.py"])
def test_asyncpg_is_allowed_in_core_database_and_the_identity_store(tmp_path, where):
    assert tree_violations(_tree(tmp_path, where, "import asyncpg\n")) == []


def test_a_different_package_with_a_similar_name_is_not_flagged(tmp_path):
    assert tree_violations(_tree(tmp_path, "api/x.py", "import redis_helpers\nimport litellm_proxy\nimport pgvector.asyncpg\n")) == []

"""Every relative link and every backticked repo path in the product docs resolves."""
import importlib.util
import subprocess

import pytest

from tests.harness import ROOT

pytestmark = pytest.mark.unit


def _load_checker():
    spec = importlib.util.spec_from_file_location("docs_check_links", ROOT / "scripts" / "docs" / "check_links.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def test_the_product_docs_have_no_broken_link_or_path():
    problems = checker.check()
    assert not problems, "\n".join(problems)


def test_the_checked_set_is_the_standard_layout():
    names = {str(p.relative_to(ROOT)) for p in checker.doc_files()}
    for expected in (
        "README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "docs/getting-started.md", "docs/architecture.md",
        "docs/configuration.md", "docs/deployment.md", "docs/operations.md", "docs/api/README.md",
        "docs/contracts/README.md", "docs/contracts/ports.md", "docs/adr/README.md", "docs/design/README.md",
    ):
        assert expected in names, expected


def _tree(tmp_path, body, extra=()):
    (tmp_path / "docs").mkdir()
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "real.py").write_text("")
    (tmp_path / "docs" / "other.md").write_text("")
    for name in extra:
        (tmp_path / name).write_text("")
    doc = tmp_path / "docs" / "page.md"
    doc.write_text(body)
    return doc


def test_a_broken_link_and_a_missing_path_are_found(tmp_path):
    doc = _tree(tmp_path, "[ok](other.md) [bad](missing.md) `core/real.py` `core/gone.py` `other.md` `gone.md`\n")
    problems = checker.check_file(doc, tmp_path)
    assert len(problems) == 3
    assert any("missing.md" in p for p in problems) and any("core/gone.py" in p for p in problems)
    assert any("gone.md" in p for p in problems)


def test_urls_anchors_routes_models_globs_and_code_fences_are_allowed(tmp_path):
    body = (
        "[a](https://example.com/x) [b](#section) [c](other.md#part) `/v1/search` `gemini/gemini-embedding-001` "
        "`core/*.py` `core/<name>.py` `python -m workers`\n\n```bash\ncat core/gone.py\n```\n"
    )
    assert checker.check_file(_tree(tmp_path, body), tmp_path) == []


def test_generated_blocks_are_skipped(tmp_path):
    body = "<!-- BEGIN GENERATED: x -->\n`core/gone.py`\n<!-- END GENERATED: x -->\n"
    assert checker.check_file(_tree(tmp_path, body), tmp_path) == []


def test_git_ignored_paths_are_skipped(tmp_path):
    _tree(tmp_path, "[ok](other.md)")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("docs/learning_docs/\n")
    ignored = tmp_path / "docs" / "learning_docs"
    ignored.mkdir()
    (ignored / "broken.md").write_text("[bad](missing.md)")
    assert checker.check(tmp_path) == []
    assert "broken.md" not in checker._known_names(tmp_path)


def test_outside_git_no_paths_are_ignored(tmp_path):
    _tree(tmp_path, "[ok](other.md)")
    (tmp_path / ".gitignore").write_text("docs/learning_docs/\n")
    ignored = tmp_path / "docs" / "learning_docs"
    ignored.mkdir()
    (ignored / "broken.md").write_text("[bad](missing.md)")
    assert checker.check(tmp_path)

"""Every workflow disables tool telemetry at workflow level."""
import pytest
import yaml

from tests.harness import ROOT

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("name", ["tests.yml", "frontend.yml"])
def test_workflow_telemetry(name):
    workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    assert workflow["env"]["DEEPEVAL_TELEMETRY_OPT_OUT"] == "YES"
    assert str(workflow["env"]["DO_NOT_TRACK"]) == "1"


@pytest.mark.parametrize("name", ["tests.yml", "frontend.yml"])
def test_all_jobs_use_common_setup_and_concurrency(name):
    workflow = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    assert workflow["concurrency"]["cancel-in-progress"] is True
    for job in workflow["jobs"].values():
        assert any(step.get("uses") == "./.github/actions/setup" for step in job["steps"])


@pytest.mark.parametrize("paths,expected", [
    (["docs/operations.md", "planning/STATE.md"], (False, False)),
    (["ui/src/app.tsx"], (True, True)),
    (["docs/api/openapi.json"], (True, True)),
    (["workers/loop.py"], (True, True)),
    (["new_package/entry.py"], (True, True)),
])
def test_change_scope_never_hides_unknown_code(paths, expected):
    from scripts.ci.change_scope import scope

    assert scope(paths) == expected


def test_lint_typecheck_and_unit_jobs_do_not_gate_on_change_scope():
    workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
    for name in ("lint", "typecheck", "unit-tests"):
        job = workflow["jobs"][name]
        assert "if" not in job or "needs.changes.outputs" not in job["if"]
        assert "changes" not in job.get("needs", [])

"""Edition smoke workflow keeps CI coverage aligned with the edition registry."""
from pathlib import Path

import pytest
import yaml

from core.modules import EDITIONS

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def test_matrix_calls_the_script_for_each_edition():
    workflow = yaml.safe_load((ROOT / ".github/workflows/editions.yml").read_text())
    job = workflow["jobs"]["smoke"]
    assert job["strategy"]["matrix"]["edition"] == list(EDITIONS)
    run_commands = [step.get("run", "") for step in job["steps"]]
    assert "scripts/ci/edition_smoke.sh '${{ matrix.edition }}'" in run_commands
    assert len([command for command in run_commands if "scripts/ci/edition_smoke.sh" in command]) == 1

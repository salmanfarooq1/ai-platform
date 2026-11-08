"""Regression tests for the repository's import-linter contracts."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROOT_PACKAGES = ("api", "core", "gateway", "evidence", "ports", "adapters", "workers", "sandbox_agent")
LINTER = Path(sys.executable).with_name("lint-imports")


def _lint(cwd: Path, config: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [str(LINTER)]
    if config is not None:
        command.extend(["--config", str(config)])
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def test_tree_passes() -> None:
    result = _lint(ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "6 kept, 0 broken" in result.stdout


@pytest.mark.parametrize(
    ("case", "target", "statement", "contract_name"),
    [
        (
            "from_gateway_policy",
            "api/agent/graph.py",
            "from gateway.policy import evaluate",
            "agent and MCP code use only the gateway package API",
        ),
        (
            "from_gateway_import_policy",
            "api/agent/graph.py",
            "from gateway import policy",
            "agent and MCP code use only the gateway package API",
        ),
        (
            "evidence_imports_gateway",
            "evidence/record.py",
            "import gateway",
            "evidence does not import gateway, api or workers",
        ),
    ],
)
def test_seeded_violation_fails(tmp_path: Path, case: str, target: str, statement: str, contract_name: str) -> None:
    del case  # The parameter name supplies the required pytest case id.
    shutil.copy2(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    for package in ROOT_PACKAGES:
        shutil.copytree(
            ROOT / package,
            tmp_path / package,
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    seeded_file = tmp_path / target
    seeded_file.write_text(seeded_file.read_text(encoding="utf-8") + f"\n{statement}\n", encoding="utf-8")
    result = _lint(tmp_path, tmp_path / "pyproject.toml")

    assert result.returncode != 0
    assert contract_name in result.stdout + result.stderr


def test_ci_lint_job_runs_lint_imports() -> None:
    workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")

    lint_job_match = re.search(r"(?ms)^  lint:\n(?P<body>.*?)(?=^  [\w-]+:|\Z)", workflow)
    assert lint_job_match is not None
    lint_job = lint_job_match.group("body")
    assert "- name: Check import contracts\n      run: poetry run lint-imports" in lint_job

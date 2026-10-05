"""Sprint 008, A4: the eval regression gate. It passes on the stored baseline and fails when a score drops.

The mutation tests lower a score, once by changing what the fake model answers (the suite then really scores lower) and
once by changing the scores directly, and check that the gate fails each time and names the metric.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.eval import run_gate, suite
from tests.fakes import FakeLLM

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
BASELINE = json.loads((ROOT / "scripts/eval/baseline.json").read_text())


def run(capsys, *argv: str) -> tuple[int, str]:
    code = run_gate.main(list(argv))
    return code, capsys.readouterr().out


def test_the_suite_scores_what_the_baseline_says(capsys):
    """The baseline is the score of the unchanged code. If this fails, retrieval or generation changed: look at why,
    then raise or lower the baseline on purpose with --update-baseline in the same reviewed change."""
    code, out = run(capsys)
    assert code == 0 and out.strip().endswith("PASSED")
    assert BASELINE["suite"] == suite.SUITE and set(BASELINE["scores"]) == set(suite.METRICS)
    assert all(0.0 <= v <= 1.0 for v in BASELINE["scores"].values()) and 0 < BASELINE["tolerance"] < 0.1
    import asyncio

    assert asyncio.run(suite.run_fake()) == BASELINE["scores"]  # the run is deterministic


def test_a_mutation_that_makes_the_fake_model_answer_wrong_fails_the_gate(monkeypatch, capsys):
    """Mutation: the fake model now quotes no source and no fact. The suite really scores lower."""
    monkeypatch.setattr(FakeLLM, "_synthesize", staticmethod(
        lambda prompt: json.dumps({"answer": "No context provided.", "confidence": 0.1, "citations": []})))
    code, out = run(capsys)
    assert code == 1 and out.strip().endswith("FAILED")
    assert "REGRESSION answer_fact" in out and "REGRESSION citation_ok" in out
    assert "REGRESSION retrieval_hit" not in out  # retrieval did not change, only the answers did


def test_a_mutation_that_breaks_retrieval_fails_the_gate_on_the_retrieval_metric(monkeypatch, capsys):
    async def nothing(*args, **kwargs):
        return []

    monkeypatch.setattr(suite, "retrieve", nothing)
    code, out = run(capsys)
    assert code == 1 and "REGRESSION retrieval_hit" in out


def lowered(by: float, metric: str = "answer_fact"):
    async def scores():
        return {**BASELINE["scores"], metric: round(BASELINE["scores"][metric] - by, 4)}

    return scores


def test_a_score_lowered_by_more_than_the_tolerance_fails(monkeypatch, capsys):
    monkeypatch.setattr(suite, "run_fake", lowered(BASELINE["tolerance"] + 0.01))
    code, out = run(capsys)
    assert code == 1 and "REGRESSION answer_fact" in out and "FAILED" in out


def test_a_score_lowered_within_the_tolerance_passes_and_a_higher_one_is_reported(monkeypatch, capsys):
    monkeypatch.setattr(suite, "run_fake", lowered(BASELINE["tolerance"] / 2))
    assert run(capsys)[0] == 0
    monkeypatch.setattr(suite, "run_fake", lowered(-0.1))
    code, out = run(capsys)
    assert code == 0 and "higher than the baseline" in out


def test_the_boundary_is_exact():
    base = {"m": 0.8}
    assert run_gate.compare({"m": 0.78}, base, 0.02) == []  # exactly baseline - tolerance passes
    assert [r.metric for r in run_gate.compare({"m": 0.7799}, base, 0.02)] == ["m"]
    assert [r.metric for r in run_gate.compare({}, base, 0.02)] == ["m"]  # a missing metric fails
    assert "missing" in str(run_gate.compare({}, base, 0.02)[0])


def test_a_baseline_raised_above_the_score_fails(tmp_path, capsys):
    raised = {**BASELINE, "scores": {k: 1.0 for k in BASELINE["scores"]}}
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(raised))
    code, out = run(capsys, "--baseline", str(path))
    assert code == 1 and out.count("REGRESSION") == 3


def test_a_bad_baseline_is_a_usage_error_not_a_pass(tmp_path, capsys):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"scores": {}}))
    assert run_gate.main(["--baseline", str(path)]) == 2
    assert run_gate.main(["--baseline", str(tmp_path / "missing.json")]) == 2
    assert "error:" in capsys.readouterr().err


def test_update_baseline_writes_only_the_file_it_is_given(tmp_path, capsys):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({**BASELINE, "scores": {k: 0.5 for k in BASELINE["scores"]}}))
    code, out = run(capsys, "--baseline", str(path), "--update-baseline")
    assert code == 0 and "baseline written" in out
    assert json.loads(path.read_text())["scores"] == BASELINE["scores"]
    assert json.loads((ROOT / "scripts/eval/baseline.json").read_text()) == BASELINE  # the stored one is untouched


def test_the_gate_runs_as_a_command_the_way_ci_runs_it():
    run_ = subprocess.run([sys.executable, "scripts/eval/run_gate.py"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert run_.returncode == 0 and run_.stdout.strip().endswith("PASSED"), run_.stdout + run_.stderr


def test_the_real_provider_run_refuses_to_start_without_an_explicit_flag():
    env = {k: v for k, v in os.environ.items() if k != "REAL_EVAL"}
    run_ = subprocess.run([sys.executable, "scripts/eval/run_real.py"], cwd=ROOT, capture_output=True, text=True, env=env, timeout=60)
    assert run_.returncode == 2 and "REAL_EVAL=1" in run_.stderr


def test_ci_runs_the_gate_and_never_the_real_run():
    import yaml

    jobs = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())["jobs"]
    commands = [step["run"] for job in jobs.values() for step in job["steps"] if "run" in step]
    assert any("scripts/eval/run_gate.py" in c for c in commands)
    assert not any("run_real" in c for c in commands)  # a comment may name it; no step may run it

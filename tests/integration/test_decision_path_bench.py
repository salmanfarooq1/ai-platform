"""WP10 benchmark smoke: this is an integration test because the script writes real DB records."""

import subprocess
import sys
from pathlib import Path


def test_benchmark_runs_at_tiny_size(database_url):
    del database_url  # The fixture provisions the same live-test Postgres prerequisites for the subprocess.
    script = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "decision_path.py"
    result = subprocess.run(
        [sys.executable, str(script), "--iterations", "1"],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 3
    for mode in ("serial", "8-way", "32-way"):
        line = next(item for item in lines if item.startswith(f"{mode}:"))
        assert "decisions_per_second=" in line
        assert "p50_added_ms=" in line
        assert "p95_added_ms=" in line

"""WP4, live: the real recovery drill on a real, fixture-owned default stack (Docker, restic and Postgres, and a metadata-only model runtime that refuses inference).

The test runs the same `Drill` that `scripts/verify/poc-drill.sh` runs, with its real ports: the `poc` CLI as a
subprocess, the public HTTP API and the offline receipt verifier. It needs Docker and the registry (`poc up` proves the
image indexes). A missing Docker daemon is a failure, never a skip. The drill tears its own stack down.
"""
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from scripts.verify import poc_drill

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


def test_saved_receipts_and_new_call_after_restore(tmp_path):
    stack = "t" + uuid.uuid4().hex[:8]
    lines: list[str] = []
    ports = poc_drill.real_ports(ROOT, tmp_path / "work", emit=lines.append)
    drill = poc_drill.Drill(stack, ports)
    try:
        code = drill.run()
    finally:  # a drill that died before its own teardown must still leave nothing behind
        if (ROOT / ".poc" / stack).exists():
            subprocess.run([sys.executable, str(ROOT / "scripts/poc"), "destroy", stack, "--confirm", stack],
                           cwd=ROOT, check=False, capture_output=True)
    markers = [line for line in lines if line.startswith(("PASS", "FAIL", "SKIP"))]
    assert code == 0, "\n".join(lines)
    assert not [m for m in markers if m.startswith(("FAIL", "SKIP"))]
    for required in poc_drill.REQUIRED_MARKERS:
        assert any(m.startswith(required) for m in markers), required
    report = drill.report
    # the restored database equals the backup before any new traffic
    assert report["restored_equals_backup"] is True and report["compared_tables"] > 10 and report["compared_heads"] >= 1
    # the receipt saved before the backup verifies offline after the restore, and a new deny adds a decision and a receipt
    assert report["saved_receipt_offline"] is True and report["new_receipt_offline"] is True
    assert report["new_decision_id"] != report["saved_decision_id"]
    assert report["new_decision_position"] > report["saved_decision_position"]
    # the POLICY denied the chat alias (it resolved), both times, at admission, with zero inference seen by the runtime and the usage summary
    assert report["inference_requests"] == 0 and report["usage_requests"] == 0
    assert report["deny_phases"] == ["admission", "admission"] and report["deny_reasons"] == ["model_not_allowed"] * 2
    assert not (ROOT / ".poc" / stack).exists(), "the fixture stack was not fully torn down"
    leftovers = subprocess.run(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project=ai-platform-poc-{stack}",
                                "--format", "{{.Names}}"], capture_output=True, text=True, check=True).stdout.split()
    volumes = subprocess.run(["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project=ai-platform-poc-{stack}",
                              "--format", "{{.Name}}"], capture_output=True, text=True, check=True).stdout.split()
    assert leftovers == [] and volumes == []
    assert json.dumps(lines).count("drillkey") == 0 and "KEY (shown once" not in "\n".join(lines)

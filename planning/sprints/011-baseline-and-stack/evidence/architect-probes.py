"""Reproduce review findings without changing product files or dependency state."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import yaml

from scripts.ci.change_scope import scope
from scripts.supply_chain import check_pins


def main():
    workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
    job = workflow["jobs"]["supply-chain"]
    print("H1: UI-only dependency changes")
    backend, frontend = scope(["ui/package.json", "ui/package-lock.json"])
    print(f"backend={backend}, frontend={frontend}")
    print(f"supply-chain condition: {job['if']}")
    assert not backend and frontend
    assert job["if"] == "${{ needs.changes.outputs.backend == 'true' }}"
    print("REPRODUCED: the npm licence gate and SBOM job are skipped.")

    print("\nM1: npm inventory completeness")
    lock = json.loads((ROOT / "ui/package-lock.json").read_text())
    print(f"Declared direct production dependencies: {len(lock['packages']['']['dependencies'])}")
    for label, inventory in (("empty", {}), ("incomplete", {"fixture@1.0.0": {"licenses": "MIT"}})):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/supply_chain/licence_metadata.py"), "--npm-metadata", "/dev/stdin"],
            input=json.dumps(inventory), capture_output=True, text=True, check=False,
        )
        print(f"{label}: exit={result.returncode}; {(result.stdout + result.stderr).strip()}")
        assert result.returncode == 0
    print("REPRODUCED: successful validation does not prove inventory completeness.")

    print("\nM2: digest text in a YAML comment")
    with tempfile.TemporaryDirectory(prefix="s011-pin-review-") as directory:
        root = Path(directory)
        for name in check_pins.FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((ROOT / name).read_text())
        compose = root / "docker-compose.yml"
        compose.write_text("services:\n  probe:\n    image: example/probe:latest # @sha256:" + "a" * 64 + "\n")
        reference = yaml.safe_load(compose.read_text())["services"]["probe"]["image"]
        output = io.StringIO()
        with patch.object(check_pins, "ROOT", root), contextlib.redirect_stdout(output):
            status = check_pins.main()
        print(f"Parsed image: {reference}; checker exit={status}")
        print(output.getvalue().splitlines()[-1])
        assert "@sha256:" not in reference and status == 0
    print("REPRODUCED: a mutable image passes when its comment contains digest-shaped text.")

    print("\nM3: independent supply-chain results after a licence failure")
    steps = job["steps"]
    licence = next(i for i, step in enumerate(steps) if step.get("name") == "OSI licences only")
    for step in steps[licence + 1:]:
        name = step.get("name", step.get("uses", "unnamed"))
        print(f"{name}: if={step.get('if', 'implicit success()')}")
        assert "if" not in step
    print("REPRODUCED: the known licence failure prevents SBOM upload and image scanning in this job.")


if __name__ == "__main__":
    main()

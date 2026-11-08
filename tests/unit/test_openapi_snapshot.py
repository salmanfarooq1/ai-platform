"""The committed OpenAPI snapshot must match the app. Refresh it with scripts/update_openapi.py."""
import json
import subprocess
import sys

import pytest

from api.openapi import SNAPSHOT_PATH, render_openapi
from api.versioning import UNVERSIONED_PATHS
from tests.harness import ROOT

pytestmark = pytest.mark.unit

TABLE = "TA" + "BLE"  # built at runtime so this file does not trip the DDL check itself


def test_snapshot_matches_the_app():
    assert SNAPSHOT_PATH.read_text() == render_openapi(), (
        "docs/api/openapi.json is out of date. If the API change is intended, run: "
        "poetry run python scripts/update_openapi.py"
    )


def test_rendering_is_deterministic():
    assert render_openapi() == render_openapi()


def test_every_public_route_is_versioned():
    paths = json.loads(SNAPSHOT_PATH.read_text())["paths"]
    assert paths
    # /metrics is the one documented unversioned route besides / and /health: Prometheus expects it at that path (Sprint 008)
    assert all(p.startswith("/v1/") or p in UNVERSIONED_PATHS or p == "/metrics" for p in paths)


def test_snapshot_has_typed_module_and_versioned_decision_models():
    schemas = json.loads(SNAPSHOT_PATH.read_text())["components"]["schemas"]
    assert "ModuleList" in schemas
    for schema in (schemas["DecisionDetail"], schemas["Receipt"]["properties"]["decision"]):
        if "$ref" in schema:
            schema = schemas[schema["$ref"].rsplit("/", 1)[-1]]
        properties = schema["properties"]
        assert properties["record_version"]["type"] == "integer"
        assert properties["extensions"]["type"] == "object"


def test_update_script_rewrites_the_snapshot(tmp_path):
    before = SNAPSHOT_PATH.read_text()
    SNAPSHOT_PATH.write_text("{}\n")
    try:
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "update_openapi.py")],
                             capture_output=True, text=True, cwd=ROOT)
        assert out.returncode == 0, out.stderr
        assert SNAPSHOT_PATH.read_text() == before
    finally:
        SNAPSHOT_PATH.write_text(before)


def test_ddl_check_passes_on_the_repo_and_fails_on_a_violation(tmp_path):
    script = str(ROOT / "scripts" / "check_no_ddl.sh")
    ok = subprocess.run([script, str(ROOT)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "bad.py").write_text(f'await conn.execute("create  {TABLE} sneaky (id int)")\n')
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "worse.sql").write_text(f"ALTER {TABLE} documents ADD COLUMN x int;\n")
    bad = subprocess.run([script, str(tmp_path)], capture_output=True, text=True)
    assert bad.returncode == 1
    assert "api/bad.py" in bad.stdout and "tests/worse.sql" in bad.stdout
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "bad.py").write_text(f'await conn.execute("CREATE {TABLE} sneaky (id int)")\n')
    bad_evidence = subprocess.run([script, str(tmp_path)], capture_output=True, text=True)
    assert bad_evidence.returncode == 1 and "evidence/bad.py" in bad_evidence.stdout
    (tmp_path / "evidence" / "bad.py").unlink()
    (tmp_path / "scripts" / "labs").mkdir(parents=True)
    (tmp_path / "scripts" / "labs" / "lab.py").write_text(f"CREATE {TABLE} lab (id int)\n")
    (tmp_path / "api" / "bad.py").unlink()
    (tmp_path / "tests" / "worse.sql").unlink()
    assert subprocess.run([script, str(tmp_path)], capture_output=True, text=True).returncode == 0

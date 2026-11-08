"""Exercise the review findings through workflow conditions and executable controls."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.ci.change_scope import scope
from tests.harness import ROOT

pytestmark = pytest.mark.unit
SOURCE = Path(os.environ.get("CONTROL_ROOT", ROOT))


def job_runs(condition, backend, frontend, result="success"):
    expression = condition.removeprefix("${{").removesuffix("}}").strip()
    for key, value in {"needs.changes.outputs.backend": backend,
                       "needs.changes.outputs.frontend": frontend,
                       "needs.changes.result": result}.items():
        expression = expression.replace(key, repr(value))
    expression = expression.replace("!cancelled()", "True").replace("always()", "True")
    expression = expression.replace("&&", " and ").replace("||", " or ")
    assert re.fullmatch(r"[\w\s'\"()=!.-]+", expression)
    return eval(expression, {"__builtins__": {}}, {})


@pytest.mark.parametrize("paths,expected", [
    (["ui/package-lock.json"], True), (["ui/package.json"], True),
    (["adapters/registry.py"], True), (["docs/operations.md"], False),
])
def test_only_image_scan_is_gated_by_change_scope(paths, expected):
    workflow = yaml.safe_load((SOURCE / ".github/workflows/tests.yml").read_text())
    job = workflow["jobs"]["supply-chain"]
    assert "if" not in job
    step = next(item for item in job["steps"] if item.get("id") == "checks")
    assert step["env"]["SKIP_IMAGE_SCAN"] == "${{ needs.changes.outputs.backend != 'true' && needs.changes.outputs.frontend != 'true' }}"
    backend, frontend = scope(paths)
    assert (backend or frontend) is expected


@pytest.mark.parametrize("backend,frontend,result", [("", "", "failure"), ("", "", "success")])
def test_missing_scope_does_not_skip_required_control(backend, frontend, result):
    workflow = yaml.safe_load((SOURCE / ".github/workflows/tests.yml").read_text())
    job = workflow["jobs"]["supply-chain"]
    assert "if" not in job
    validate = next(step for step in job["steps"] if step.get("name") == "Validate change scope")
    check = subprocess.run(["bash", "-e", "-c", validate["run"]], env={**os.environ,
        "SCOPE_RESULT": result, "BACKEND_SCOPE": backend, "FRONTEND_SCOPE": frontend},
        capture_output=True, text=True, timeout=5)
    assert check.returncode != 0


def fixture_root(tmp_path):
    chain = tmp_path / "scripts/supply_chain"
    chain.mkdir(parents=True)
    for name in ("licence_metadata.py", "artifact_licences.py", "osi-licences.txt", "licence-exceptions.txt"):
        shutil.copy(SOURCE / "scripts/supply_chain" / name, chain / name)
    ui = tmp_path / "ui"
    ui.mkdir()
    manifest = {"name": "ai-platform-ui", "version": "2.0.0", "private": True,
                "dependencies": {"alpha": "1.0.0", "beta": "2.0.0"}}
    (ui / "package.json").write_text(json.dumps(manifest))
    packages = {"": manifest}
    for name, version in (("alpha", "1.0.0"), ("beta", "2.0.0")):
        directory = ui / "node_modules" / name
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"name": name, "version": version}))
        packages[f"node_modules/{name}"] = {"version": version, "devOptional": True}
    packages["node_modules/optional-darwin"] = {"version": "1.0.0", "optional": True, "os": ["darwin"]}
    packages["node_modules/dev-only"] = {"version": "1.0.0", "dev": True}
    (ui / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": packages}))
    return chain, ui


@pytest.mark.parametrize("fail_build", [False, True])
@pytest.mark.parametrize("fail_scan", [False, True])
def test_image_scan_covers_flow_mapping_anchors_and_independent_builds(tmp_path, fail_build, fail_scan):
    chain = tmp_path / "scripts/supply_chain"
    chain.mkdir(parents=True)
    for name in ("image_scan.sh", "check_pins.py", "image_exceptions.py"):
        shutil.copy(SOURCE / "scripts/supply_chain" / name, chain / name)
    image = "registry.test/image:1@sha256:" + "a" * 64
    other = "registry.test/other:2@sha256:" + "b" * 64
    (tmp_path / "docker-compose.yml").write_text(
        f'x-base: &base {{image: "{image}"}}\nservices:\n'
        f'  flow: {{image: "{other}"}}\n  merged: {{<<: *base}}\n  local: {{build: .}}\n'
    )
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "calls.txt"
    for name in ("docker", "grype", "poetry"):
        path = commands / name
        path.write_text(
            f"#!{sys.executable}\nimport os,sys,subprocess\n"
            "from pathlib import Path\n"
            "if Path(sys.argv[0]).name == 'poetry':\n"
            " sys.exit(subprocess.call([sys.executable,*sys.argv[3:]]))\n"
            "if sys.argv[1:3] == ['image','inspect']: print('sha256:'+'c'*64)\n"
            "with open(os.environ['IMAGE_CALLS'],'a') as out: out.write(Path(sys.argv[0]).name+' '+' '.join(sys.argv[1:])+'\\n')\n"
            "if Path(sys.argv[0]).name == 'docker' and sys.argv[1] == 'compose' and os.environ.get('FAIL_BUILD') == '1': sys.exit(1)\n"
            "if Path(sys.argv[0]).name == 'grype' and os.environ.get('FAIL_SCAN') == '1': sys.exit(2)\n"
        )
        path.chmod(0o755)
    env = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"], "IMAGE_CALLS": str(log),
           "FAIL_BUILD": "1" if fail_build else "0", "FAIL_SCAN": "1" if fail_scan else "0"}
    result = subprocess.run(["bash", str(chain / "image_scan.sh")], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == int(fail_build or fail_scan), result.stdout + result.stderr
    calls = log.read_text()
    for reference in (image, other):
        assert f"docker pull {reference}\n" in calls
        assert "docker image inspect --format {{.Id}} " + reference + "\n" in calls
    # Labels remain in the identity ledger; scans consume immutable IDs, never mutable tags.
    assert "grype docker:sha256:" + "c" * 64 + " " in calls
    assert "--only-fixed --fail-on critical" in calls
    assert "docker build -f ui/Dockerfile.ui -t gap-supply-chain:ui ui/" in calls
    assert calls.count("grype ") == 1  # Every fake alias resolves to the same immutable artifact.
    ledger = (tmp_path / "sbom/checks/images/identities.tsv").read_text()
    assert image in ledger and other in ledger
    assert "docker:gap-supply-chain:ui\t" in ledger
    assert "docker compose --project-name gap-supply-chain --profile * build local\n" in calls
    assert ("docker:gap-supply-chain-local\t" in ledger) is not fail_build


@pytest.mark.parametrize("instruction,valid", [
    ("FROM alpine:latest", False),
    ("FROM alpine:3@sha256:" + "a" * 64, True),
    ("FROM scratch\nCOPY --from=alpine:latest /file /file", False),
    ("FROM scratch\nCOPY --from=alpine:3@sha256:" + "a" * 64 + " /file /file", True),
])
def test_service_dockerfiles_and_external_copy_images_are_pinned(tmp_path, instruction, valid):
    from scripts.supply_chain.check_pins import REFERENCE, references

    dockerfile = tmp_path / "docker/service.Dockerfile"
    dockerfile.parent.mkdir()
    dockerfile.write_text(instruction + "\n")
    (tmp_path / "Dockerfile").write_text("")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    for name in ("tests.yml", "frontend.yml"):
        (workflows / name).write_text("jobs: {}\n")
    images = list(references(tmp_path))
    assert all(REFERENCE.fullmatch(image) for _, image in images) is valid


@pytest.mark.parametrize("mode", ["--npm-metadata", "--npm-ignored"])
@pytest.mark.parametrize("inventory,valid", [
    ({}, False), ({"alpha@1.0.0": {"licenses": "MIT"}}, False),
    ({"alpha@9.0.0": {"licenses": "MIT"}, "beta@2.0.0": {"licenses": "MIT"}}, False),
    ({"alpha@1.0.0": {"licenses": "MIT"}, "beta@2.0.0": {"licenses": "MIT"},
      "extra@1.0.0": {"licenses": "MIT"}}, False),
    ({"alpha@1.0.0": {"licenses": "MIT"}, "beta@2.0.0": {"licenses": "MIT"}}, True),
])
def test_npm_cli_requires_exact_installed_production_inventory(tmp_path, mode, inventory, valid):
    chain, _ = fixture_root(tmp_path)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(inventory))
    result = subprocess.run([sys.executable, str(chain / "licence_metadata.py"), mode, str(metadata)],
                            capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) is valid, result.stdout + result.stderr


def test_missing_required_installation_fails_even_with_complete_metadata(tmp_path):
    chain, ui = fixture_root(tmp_path)
    (ui / "node_modules/beta/package.json").unlink()
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"alpha@1.0.0": {"licenses": "MIT"}, "beta@2.0.0": {"licenses": "MIT"}}))
    result = subprocess.run([sys.executable, str(chain / "licence_metadata.py"), "--npm-metadata", str(metadata)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0


@pytest.mark.parametrize("image,valid", [
    ('example/probe:latest # @sha256:' + 'a' * 64, False),
    ('"example/probe:latest" # @sha256:' + 'a' * 64, False),
    ('example/probe:v1@sha256:' + 'a' * 63, False),
    ('example/probe:v1@sha256:' + 'a' * 64 + 'extra', False),
    ('"example/probe:v1@sha256:' + 'a' * 64 + '" # approved', True),
])
@pytest.mark.parametrize("kind", ["compose", "workflow", "dockerfile"])
def test_only_parsed_image_references_count(tmp_path, image, valid, kind):
    chain = tmp_path / "scripts/supply_chain"
    chain.mkdir(parents=True)
    shutil.copy(SOURCE / "scripts/supply_chain/check_pins.py", chain / "check_pins.py")
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (workflows / "tests.yml").write_text("jobs: {}\n")
    (workflows / "frontend.yml").write_text("jobs: {}\n")
    (tmp_path / "Dockerfile").write_text("")
    if kind == "compose":
        (tmp_path / "docker-compose.yml").write_text("services:\n  probe:\n    image: " + image + "\n")
    elif kind == "workflow":
        (workflows / "tests.yml").write_text("jobs:\n  test:\n    services:\n      probe:\n        image: " + image + "\n")
    else:
        (tmp_path / "Dockerfile").write_text("RUN echo hello \\\n world\nFROM --platform=linux/amd64 " + image + "\n")
    result = subprocess.run([sys.executable, str(chain / "check_pins.py")], capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) is valid, result.stdout + result.stderr


@pytest.mark.parametrize("extra_compose", [
    "docker-compose.prod.yml", "compose.yaml", "docker-compose.override.yml",
])
@pytest.mark.parametrize("mode", [[], ["--compose-images"], ["--built-services"]])
def test_pin_cli_rejects_unregistered_root_compose_before_listing_images(tmp_path, extra_compose, mode):
    chain = tmp_path / "scripts/supply_chain"
    chain.mkdir(parents=True)
    shutil.copy(SOURCE / "scripts/supply_chain/check_pins.py", chain / "check_pins.py")
    image = "registry.test/image:1@sha256:" + "a" * 64
    (tmp_path / "docker-compose.yml").write_text(
        f'services:\n  pinned:\n    image: "{image}"\n  local:\n    build: .\n'
    )
    (tmp_path / extra_compose).write_text("services: {}\n")
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    for name in ("tests.yml", "frontend.yml"):
        (workflows / name).write_text("jobs: {}\n")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")

    result = subprocess.run(
        [sys.executable, str(chain / "check_pins.py"), *mode],
        capture_output=True, text=True, timeout=10,
    )

    assert result.returncode != 0
    assert extra_compose in result.stdout
    assert image not in result.stdout


@pytest.mark.parametrize("directive", ["include", "extends"])
@pytest.mark.parametrize("mode", [[], ["--compose-images"], ["--built-services"]])
def test_pin_cli_rejects_unregistered_compose_indirection_before_listing_images(
    tmp_path, directive, mode,
):
    chain = tmp_path / "scripts/supply_chain"
    chain.mkdir(parents=True)
    shutil.copy(SOURCE / "scripts/supply_chain/check_pins.py", chain / "check_pins.py")
    image = "registry.test/image:1@sha256:" + "a" * 64
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker/compose-fragment.yaml").write_text(
        "services:\n  fragment:\n    image: registry.test/fragment:1@sha256:" + "b" * 64 + "\n"
    )
    compose = f"services:\n  pinned:\n    image: \"{image}\"\n  local:\n    build: .\n"
    if directive == "include":
        compose = "include:\n  - ./docker/compose-fragment.yaml\n" + compose
    else:
        compose += (
            "  inherited:\n    extends:\n      file: ./docker/compose-fragment.yaml\n"
            "      service: fragment\n"
        )
    (tmp_path / "docker-compose.yml").write_text(compose)
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    for name in ("tests.yml", "frontend.yml"):
        (workflows / name).write_text("jobs: {}\n")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")

    result = subprocess.run(
        [sys.executable, str(chain / "check_pins.py"), *mode],
        capture_output=True, text=True, timeout=10,
    )

    assert result.returncode != 0
    assert directive in result.stdout
    assert image not in result.stdout


def test_licence_failure_keeps_independent_controls_and_upload_eligible(tmp_path):
    chain = tmp_path / "scripts/supply_chain"
    chain.mkdir(parents=True)
    shutil.copy(SOURCE / "scripts/supply_chain/run_checks.sh", chain / "run_checks.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for name, code in (("export_locks.sh", 0), ("licence_gate.sh", 1), ("sbom.sh", 0),
                       ("install_scanners.sh", 0), ("image_scan.sh", 0)):
        stub = chain / name
        stub.write_text(f'#!/bin/sh\necho {name} >> "$CALLS"\nexit {code}\n')
        stub.chmod(0o755)
    poetry = bin_dir / "poetry"
    poetry.write_text('#!/bin/sh\necho pins >> "$CALLS"\nexit 0\n')
    poetry.chmod(0o755)
    result = subprocess.run(["bash", str(chain / "run_checks.sh")], env={**os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "CALLS": str(calls)},
        capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert calls.read_text().splitlines() == ["export_locks.sh", "pins", "licence_gate.sh", "sbom.sh",
                                            "install_scanners.sh", "image_scan.sh"]
    workflow = yaml.safe_load((SOURCE / ".github/workflows/tests.yml").read_text())
    steps = workflow["jobs"]["supply-chain"]["steps"]
    runner = next(step for step in steps if step.get("id") == "checks")
    assert "run_checks.sh" in runner["run"]
    upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact"))
    assert "!cancelled()" in upload["if"] or "always()" in upload["if"]
    upload_condition = upload["if"].replace("steps.checks.outcome", "'failure'")
    assert job_runs(upload_condition, "true", "false")
    assert not any(step.get("continue-on-error") for step in steps)


def test_unpinned_ui_dockerfile_is_rejected(tmp_path):
    chain = tmp_path / "scripts/supply_chain"
    chain.mkdir(parents=True)
    shutil.copy(SOURCE / "scripts/supply_chain/check_pins.py", chain / "check_pins.py")
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    for name in ("tests.yml", "frontend.yml"):
        (workflows / name).write_text("jobs: {}\n")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "Dockerfile.ui").write_text("FROM node:22-alpine\n")
    result = subprocess.run([sys.executable, str(chain / "check_pins.py")], capture_output=True, text=True)
    assert result.returncode == 1
    assert "ui/Dockerfile.ui:1: expected a tag and complete sha256 digest" in result.stdout


def test_build_inventory_keeps_only_worker_and_app_dockerfile():
    from scripts.supply_chain.check_pins import built_services, dockerfile_references

    assert built_services(ROOT) == ["worker"]
    app_images = [image for location, image in dockerfile_references(ROOT, ROOT / "Dockerfile")
                  if location.startswith("Dockerfile:")]
    assert len(app_images) == 2

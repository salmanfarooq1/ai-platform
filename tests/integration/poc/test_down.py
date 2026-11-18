"""WP3 live: teardown ownership against real Docker volumes. Only this module's own throw-away volumes are created or removed."""
import fcntl
import json
import os
import shutil
import subprocess
import uuid

import pytest

from scripts.poc_lib import lifecycle
from scripts.poc_lib import up as poc_up
from scripts.poc_lib.keys import ensure_stack_secrets
from scripts.poc_lib.runner import LocalRunner
from scripts.poc_lib.up import PocError
from tests.integration.poc.conftest import ROOT

PROTECTED = ("ai-platform_pgdata", "ai-platform_pgdata_trixie")
PROOF = lifecycle.DownProof


def _docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def _volume_exists(name: str) -> bool:
    return _docker("volume", "inspect", name, check=False).returncode == 0


@pytest.fixture
def owned_stack():
    """A marker and secrets for a stack that has no containers, plus the right to create its three named volumes."""
    name = "td" + uuid.uuid4().hex[:8]
    ensure_stack_secrets(ROOT, name)
    folder = ROOT / ".poc" / name
    marker = poc_up._expected_marker(name, 18999)
    poc_up._write_private(folder / "marker.json", json.dumps(marker, sort_keys=True) + "\n", replace=False)
    created: list[str] = []

    def make_volume(volume: str, *, labels: dict | None = None, options: dict | None = None) -> None:
        command = ["volume", "create"]
        for key, value in (labels or {}).items():
            command += ["--label", f"{key}={value}"]
        for key, value in (options or {}).items():
            command += ["--opt", f"{key}={value}"]
        _docker(*command, volume)
        created.append(volume)

    try:
        yield name, marker, make_volume
    finally:
        for volume in created:  # only volumes this fixture created, by exact name
            assert volume.startswith("ai-platform-poc-td")
            _docker("volume", "rm", "-f", volume, check=False)
        shutil.rmtree(folder, ignore_errors=True)


def _destroy(name):
    context = lifecycle.load_context(ROOT, name, runner=LocalRunner(), environ=dict(os.environ))
    lifecycle.RealBackend(context).destroy(PROOF(name, "a" * 64, "b" * 64))


def test_down_never_touches_dev_project_volumes(owned_stack):
    name, marker, make_volume = owned_stack
    project = marker["project"]
    before = {v: _volume_exists(v) for v in PROTECTED}
    # Marker volumes that carry the developer project's label: down refuses and removes nothing.
    make_volume(f"{project}_objects", labels={"com.docker.compose.project": "ai-platform"})
    make_volume(f"{project}_pgdata_trixie", labels={"com.docker.compose.project": project})
    make_volume(f"{project}_valkey_data", labels={"com.docker.compose.project": project})
    with pytest.raises(PocError, match="volume"):
        _destroy(name)
    assert all(_volume_exists(f"{project}_{v}") for v in ("objects", "pgdata_trixie", "valkey_data"))
    # A marker that lists a developer volume is refused as a whole, before any engine call.
    marker_path = ROOT / ".poc" / name / "marker.json"
    text = marker_path.read_text().replace(f"{project}_pgdata_trixie", "ai-platform_pgdata_trixie")
    marker_path.write_text(text)
    with pytest.raises(PocError, match="marker"):
        _destroy(name)
    assert {v: _volume_exists(v) for v in PROTECTED} == before  # the developer volumes are exactly as they were


def test_ownership_and_lifecycle_races_refuse(owned_stack):
    name, marker, make_volume = owned_stack
    project = marker["project"]
    label = {"com.docker.compose.project": project}
    # A volume that is really a bind of a host folder (a symlink in effect) is not ours to delete through Docker.
    make_volume(f"{project}_objects", labels=label, options={"type": "none", "o": "bind", "device": "/tmp"})
    make_volume(f"{project}_pgdata_trixie", labels=label)
    make_volume(f"{project}_valkey_data", labels=label)
    with pytest.raises(PocError, match="volume"):
        _destroy(name)
    assert all(_volume_exists(f"{project}_{v}") for v in ("objects", "pgdata_trixie", "valkey_data"))
    assert os.path.exists("/tmp")

    # Another lifecycle command is running (a restore, a backup or a second down): refuse, touch nothing.
    class Recorder:
        calls: list[str] = []

        def __getattr__(self, method):
            def record(*args, **kwargs):
                Recorder.calls.append(method)
                raise AssertionError("the backend must not be used while another lifecycle command holds the lock")
            return record

    descriptor = os.open(ROOT / ".poc" / ".locks" / f"{name}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with pytest.raises(PocError, match="another"):
            lifecycle.down(ROOT, name, runner=LocalRunner(), environ={**os.environ, "POC_RECOVERY_REF": "x"}, backend=Recorder())
        with pytest.raises(PocError, match="another"):
            lifecycle.backup(ROOT, name, runner=LocalRunner(), environ=dict(os.environ))
    finally:
        os.close(descriptor)
    assert Recorder.calls == []
    assert all(_volume_exists(f"{project}_{v}") for v in ("objects", "pgdata_trixie", "valkey_data"))

    # An owner mismatch: a marker written for another stack is never adopted.
    other = poc_up._expected_marker("td-other", 18999)
    (ROOT / ".poc" / name / "marker.json").write_text(json.dumps(other, sort_keys=True) + "\n")
    with pytest.raises(PocError, match="marker"):
        _destroy(name)
    assert all(_volume_exists(f"{project}_{v}") for v in ("objects", "pgdata_trixie", "valkey_data"))

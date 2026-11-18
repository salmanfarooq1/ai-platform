"""WP3: the local POC lifecycle commands. Names, order and refusals; no Docker is needed (fake Runner and fake backend)."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.poc_backup.model import BackupRef, DbState
from scripts.poc_lib import lifecycle
from scripts.poc_lib import up as poc_up
from scripts.poc_lib.keys import ensure_stack_secrets
from scripts.poc_lib.runner import LocalRunner, Result
from scripts.poc_lib.up import PocError

NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
STATE = DbState(schema_head="0011", counts={"tenants": 1, "jobs": 3}, heads=[["t1", 4, "a" * 64]],
                checkpoints=[["t1", 0, "b" * 64, "genesis"]], objects=[])
SNAPSHOT = "a1b2c3d4" * 8
MANIFEST_SHA = "c" * 64


class NoCalls:
    """A runner that fails the test when any tool is called."""

    def __init__(self):
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(list(argv))
        raise AssertionError(f"a tool was called before validation finished: {argv[:3]}")


class LocalDocker:
    """Answers the two `docker context` probes of the local-engine check; records everything else."""

    def __init__(self):
        self.calls = []

    def run(self, argv, **kwargs):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:3] == ["docker", "context", "show"]:
            return Result(0, b"default\n")
        return Result(0, b"")


def make_stack(root: Path, stack="demo", port=18321) -> Path:
    """A stack folder as the first `poc up` leaves it: private secrets and the marker."""
    ensure_stack_secrets(root, stack)
    marker = poc_up._expected_marker(stack, port)
    poc_up._write_private(root / ".poc" / stack / "marker.json", json.dumps(marker, sort_keys=True) + "\n", replace=False)
    return root / ".poc" / stack


def ref(**changes) -> BackupRef:
    values = dict(stack="demo", snapshot_id=SNAPSHOT, manifest_sha256=MANIFEST_SHA, created_at=NOW - timedelta(seconds=60),
                  state=STATE)
    values.update(changes)
    return BackupRef(**values)


class FakeBackend:
    def __init__(self, *, latest=None, live=STATE, verify_error=None, latest_changes=None):
        self.calls = []
        self._latest = ref() if latest is None else latest
        self._latest_changes = latest_changes  # the ref returned by the second latest() call
        self.live = live
        self.verify_error = verify_error
        self.latest_calls = 0
        self.destroyed_with = None

    def stop_writers(self):
        self.calls.append("stop_writers")

    def start_writers(self):
        self.calls.append("start_writers")

    def latest(self):
        self.calls.append("latest")
        self.latest_calls += 1
        if self.latest_calls > 1 and self._latest_changes is not None:
            return self._latest_changes
        return self._latest

    def live_state(self):
        self.calls.append("live_state")
        return self.live

    def verify(self, backup_ref):
        self.calls.append("verify")
        if self.verify_error:
            raise PocError(self.verify_error)

    def destroy(self, proof):
        self.calls.append("destroy")
        self.destroyed_with = proof


def run_down(tmp_path, backend, *, environ=None, now=NOW, stack="demo"):
    env = {"PATH": "/usr/bin", "POC_RECOVERY_REF": SNAPSHOT}
    env.update(environ or {})
    return lifecycle.down(tmp_path, stack, runner=LocalDocker(), environ=env, clock=lambda: now, backend=backend)


# --- stack name, marker, local runner --------------------------------------------------------------------------------

BAD_NAMES = ["", "ab", "Abc", "1abc", "a" * 32, "../x", "a/b", "a b", "a_b", "abc;rm", "abc\n", "-abc", ".hidden"]


@pytest.mark.parametrize("name", BAD_NAMES)
@pytest.mark.parametrize("command", ["up", "backup", "down", "status"])
def test_stack_name_marker_and_local_runner(name, command, tmp_path):
    runner = NoCalls()
    function = getattr(lifecycle if command != "up" else poc_up, command)
    with pytest.raises(ValueError):
        function(tmp_path, name, runner=runner)
    assert runner.calls == []
    assert not (tmp_path / ".poc").exists() or not any((tmp_path / ".poc").iterdir())


def test_remote_context_and_missing_marker_refuse_before_tool_calls(tmp_path):
    runner = NoCalls()
    for command in ("backup", "down", "status"):
        with pytest.raises(PocError, match="remote Docker"):
            getattr(lifecycle, command)(tmp_path, "demo", runner=runner, environ={"DOCKER_HOST": "tcp://10.0.0.5:2375"})
    assert runner.calls == []
    # A local engine but no marker: the stack was never brought up here. Nothing may be created or started.
    docker = LocalDocker()
    for command in ("backup", "down", "status"):
        with pytest.raises(PocError, match="marker"):
            getattr(lifecycle, command)(tmp_path, "demo", runner=docker, environ={"PATH": "/usr/bin"})
    assert [c for c in docker.calls if c[:2] == ["docker", "compose"]] == []
    assert not (tmp_path / ".poc").exists()


def test_foreign_or_unsafe_marker_refuses(tmp_path):
    folder = make_stack(tmp_path)
    marker = folder / "marker.json"
    original = marker.read_text()
    docker = LocalDocker()
    cases = {
        "other project": original.replace("ai-platform-poc-demo", "ai-platform"),
        "dev volume": original.replace("ai-platform-poc-demo_pgdata_trixie", "ai-platform_pgdata"),
        "extra field": original.replace("}", ', "volumes_extra": []}'),
        "not json": "{",
    }
    for label, text in cases.items():
        marker.write_text(text)
        with pytest.raises(PocError, match="marker"):
            lifecycle.down(tmp_path, "demo", runner=docker, environ={"PATH": "/usr/bin"}, backend=FakeBackend())
        marker.chmod(0o600)
    marker.write_text(original)
    marker.chmod(0o644)  # not private: refused, never adopted
    with pytest.raises(PocError, match="marker"):
        lifecycle.down(tmp_path, "demo", runner=docker, environ={"PATH": "/usr/bin"}, backend=FakeBackend())
    marker.chmod(0o600)
    marker.unlink()
    marker.symlink_to(folder / "restic-password")
    with pytest.raises(PocError, match="marker"):
        lifecycle.down(tmp_path, "demo", runner=docker, environ={"PATH": "/usr/bin"}, backend=FakeBackend())


def test_runner_uses_argument_arrays_and_never_a_shell(monkeypatch):
    seen = {}
    real = subprocess.run

    def spy(argv, **kwargs):
        seen["argv"], seen["shell"] = argv, kwargs.get("shell")
        return real(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    hostile = "x; echo INJECTED > /dev/null && $(id)"
    result = LocalRunner().run(["echo", hostile])
    assert seen["shell"] is False and isinstance(seen["argv"], list)
    assert result.text.strip() == hostile  # the metacharacters stayed data


# --- down: the checks, in order --------------------------------------------------------------------------------------

def test_down_checks_in_order(tmp_path):
    make_stack(tmp_path)
    # Success: writers stop first, then latest ref, live state, (age is pure), the read-data check, a recheck, destroy.
    backend = FakeBackend()
    proof = run_down(tmp_path, backend)
    assert backend.calls == ["stop_writers", "latest", "live_state", "verify", "latest", "destroy"]
    assert proof.snapshot_id == SNAPSHOT and proof.manifest_sha256 == MANIFEST_SHA
    assert backend.destroyed_with == proof

    # Every refusal restarts the writers, never destroys, and never reaches a later gate.
    refusals = {
        "ref": (dict(environ={"POC_RECOVERY_REF": "deadbeef"}), {}, ["stop_writers", "latest"], "latest backup"),
        "live": ({}, dict(live=DbState("0011", {"tenants": 1, "jobs": 4}, STATE.heads, STATE.checkpoints, [])),
                 ["stop_writers", "latest", "live_state"], "data written after backup; run poc backup"),
        "age": (dict(now=NOW + timedelta(days=3)), {}, ["stop_writers", "latest", "live_state"], "too old"),
        "verify": ({}, dict(verify_error="restic check failed"), ["stop_writers", "latest", "live_state", "verify"],
                   "restic check failed"),
        "changed": ({}, dict(latest_changes=ref(snapshot_id="f" * 64)),
                    ["stop_writers", "latest", "live_state", "verify", "latest"], "changed"),
    }
    for label, (kwargs, backend_args, expected, message) in refusals.items():
        backend = FakeBackend(**backend_args)
        with pytest.raises(PocError, match=message):
            run_down(tmp_path, backend, **kwargs)
        assert backend.calls == [*expected, "start_writers"], label
        assert "destroy" not in backend.calls

    # The order itself: with several failures at once the earliest gate in the contract speaks.
    both = FakeBackend(live=DbState("0011", {"tenants": 9}, STATE.heads, STATE.checkpoints, []), verify_error="restic check failed")
    with pytest.raises(PocError, match="data written after backup"):
        run_down(tmp_path, both, now=NOW + timedelta(days=3))
    assert "verify" not in both.calls
    wrong_ref_and_stale = FakeBackend()
    with pytest.raises(PocError, match="latest backup"):
        run_down(tmp_path, wrong_ref_and_stale, environ={"POC_RECOVERY_REF": "nope"}, now=NOW + timedelta(days=3))
    assert "live_state" not in wrong_ref_and_stale.calls


def test_down_refuses_writes_after_backup(tmp_path):
    make_stack(tmp_path)
    changed = {
        "row count": DbState("0011", {"tenants": 1, "jobs": 4}, STATE.heads, STATE.checkpoints, []),
        "new table": DbState("0011", {"tenants": 1, "jobs": 3, "usage_log": 1}, STATE.heads, STATE.checkpoints, []),
        "chain head position": DbState("0011", STATE.counts, [["t1", 5, "a" * 64]], STATE.checkpoints, []),
        "chain head hash": DbState("0011", STATE.counts, [["t1", 4, "d" * 64]], STATE.checkpoints, []),
        "new tenant chain": DbState("0011", STATE.counts, [*STATE.heads, ["t2", 0, "e" * 64]], STATE.checkpoints, []),
        "checkpoint": DbState("0011", STATE.counts, STATE.heads, [*STATE.checkpoints, ["t1", 3, "f" * 64, "purge"]], []),
        "schema head": DbState("0012", STATE.counts, STATE.heads, STATE.checkpoints, []),  # fix round 1: gate 3 compares it
        "new object": DbState("0011", STATE.counts, STATE.heads, STATE.checkpoints, ["d" * 64]),  # ... and the object list
    }
    for label, live in changed.items():
        backend = FakeBackend(live=live)
        with pytest.raises(PocError, match="data written after backup; run poc backup"):
            run_down(tmp_path, backend)
        assert backend.calls == ["stop_writers", "latest", "live_state", "start_writers"], label
    # Equal state passes, whatever the order the database returned (counts, heads, checkpoints and the object list).
    keys = ["1" * 64, "2" * 64]
    stored = ref(state=DbState("0011", STATE.counts, STATE.heads, STATE.checkpoints, keys))
    shuffled = DbState("0011", {"jobs": 3, "tenants": 1}, STATE.heads, STATE.checkpoints, list(reversed(keys)))
    backend = FakeBackend(latest=stored, live=shuffled)
    run_down(tmp_path, backend)
    assert backend.calls[-1] == "destroy"
    missing = DbState("0011", STATE.counts, STATE.heads, STATE.checkpoints, keys[:1])  # an object reference disappeared
    backend = FakeBackend(latest=stored, live=missing)
    with pytest.raises(PocError, match="data written after backup; run poc backup"):
        run_down(tmp_path, backend)
    assert "destroy" not in backend.calls


@pytest.mark.parametrize(("environ", "age", "passes"), [
    ({}, 86400, True),  # the default is 24 hours and the exact boundary passes
    ({}, 86401, False),
    ({"POC_BACKUP_MAX_AGE_SECONDS": "600"}, 600, True),
    ({"POC_BACKUP_MAX_AGE_SECONDS": "600"}, 601, False),
    ({"POC_BACKUP_MAX_AGE_SECONDS": "172800"}, 100000, True),
    ({"POC_BACKUP_MAX_AGE_SECONDS": "0"}, 0, False),
    ({"POC_BACKUP_MAX_AGE_SECONDS": "-5"}, 1, False),
    ({"POC_BACKUP_MAX_AGE_SECONDS": "abc"}, 1, False),
    ({"POC_BACKUP_MAX_AGE_SECONDS": ""}, 1, False),
    ({"POC_BACKUP_MAX_AGE_SECONDS": "1.5"}, 1, False),
    ({}, -1, False),  # a backup dated in the future is never fresh
])
def test_stale_backup_refuses_down(tmp_path, environ, age, passes):
    make_stack(tmp_path)
    backend = FakeBackend(latest=ref(created_at=NOW - timedelta(seconds=age)))
    if passes:
        run_down(tmp_path, backend, environ=environ)
        assert backend.calls[-1] == "destroy"
    else:
        with pytest.raises(PocError):
            run_down(tmp_path, backend, environ=environ)
        assert backend.calls[-1] == "start_writers" and "destroy" not in backend.calls
        assert "verify" not in backend.calls


def test_recovery_ref_must_be_latest(tmp_path):
    make_stack(tmp_path)
    cases = {
        "missing": (dict(environ={"POC_RECOVERY_REF": ""}), FakeBackend()),
        "older": (dict(environ={"POC_RECOVERY_REF": "0" * 64}), FakeBackend()),
        "no backup at all": ({}, FakeBackend(latest=False)),
        "wrong stack": ({}, FakeBackend(latest=ref(stack="other"))),
        "prefix too short": (dict(environ={"POC_RECOVERY_REF": SNAPSHOT[:3]}), FakeBackend()),
    }
    for label, (kwargs, backend) in cases.items():
        if backend._latest is False:
            backend.latest = lambda b=backend: (b.calls.append("latest"), None)[1]
        with pytest.raises(PocError):
            run_down(tmp_path, backend, **kwargs)
        assert "destroy" not in backend.calls and "live_state" not in backend.calls, label
        assert backend.calls[-1] == "start_writers", label
    env_unset = FakeBackend()
    with pytest.raises(PocError, match="POC_RECOVERY_REF"):
        lifecycle.down(tmp_path, "demo", runner=LocalDocker(), environ={"PATH": "/usr/bin"}, clock=lambda: NOW,
                       backend=env_unset)
    # The printed short id (8 characters of the snapshot id) is accepted and the proof binds the full digests.
    backend = FakeBackend()
    proof = run_down(tmp_path, backend, environ={"POC_RECOVERY_REF": SNAPSHOT[:8]})
    assert (proof.snapshot_id, proof.manifest_sha256, proof.stack) == (SNAPSHOT, MANIFEST_SHA, "demo")


# --- teardown removes only what the marker owns ------------------------------------------------------------------------

class VolumeDocker:
    """A fake engine with labelled volumes; records every command."""

    def __init__(self, labels, options=None, fail_rm=(), ghost=()):
        self.calls = []
        self.labels = dict(labels)
        self.options = options or {}
        self.removed = []
        self.fail_rm = set(fail_rm)  # `docker volume rm` exits non-zero for these
        self.ghost = set(ghost)  # `docker volume rm` says success but the volume stays

    def run(self, argv, **kwargs):
        argv = list(argv)
        self.calls.append(argv)
        if argv[:3] == ["docker", "context", "show"]:
            return Result(0, b"default\n")
        if argv[:3] == ["docker", "volume", "inspect"]:
            name = argv[-1]
            if name not in self.labels:
                return Result(1, b"", b"no such volume")
            info = {"Name": name, "Driver": "local", "Labels": self.labels[name], "Options": self.options.get(name),
                    "Mountpoint": f"/var/lib/docker/volumes/{name}/_data"}
            return Result(0, json.dumps([info]).encode())
        if argv[:3] == ["docker", "volume", "rm"]:
            self.removed.append(argv[-1])
            if argv[-1] in self.fail_rm:
                return Result(1, b"", b"volume is in use")
            if argv[-1] not in self.ghost:
                self.labels.pop(argv[-1], None)  # a removed volume is gone: a later inspect fails
            return Result(0, b"")
        return Result(0, b"")


def owned_labels(project="ai-platform-poc-demo"):
    return {f"{project}_{name}": {"com.docker.compose.project": project}
            for name in ("objects", "pgdata_trixie", "valkey_data")}


def test_destroy_removes_only_owned_volumes_and_keeps_secrets_backups_and_marker(tmp_path):
    folder = make_stack(tmp_path)
    (folder / "backups").mkdir()
    (folder / "backups" / "config").write_text("repository")
    docker = VolumeDocker(owned_labels())
    context = lifecycle.load_context(tmp_path, "demo", runner=docker, environ={"PATH": "/usr/bin"})
    lifecycle.RealBackend(context).destroy(lifecycle.DownProof("demo", SNAPSHOT, MANIFEST_SHA))
    assert sorted(docker.removed) == sorted(owned_labels())
    compose = [c for c in docker.calls if c[:2] == ["docker", "compose"]]
    assert compose and all("--volumes" not in c and "-v" not in c for c in compose)  # volumes go by name, never by prune
    assert not any(c[:3] in (["docker", "system", "prune"], ["docker", "volume", "prune"]) for c in docker.calls)
    for kept in ("receipt-signing.key", "restic-password", "marker.json", "backups/config"):
        assert (folder / kept).exists(), kept


def test_destroy_refuses_foreign_labelled_or_bind_volumes_before_removing_any(tmp_path):
    make_stack(tmp_path)
    project = "ai-platform-poc-demo"
    scenarios = {
        "dev project label": {**owned_labels(), f"{project}_objects": {"com.docker.compose.project": "ai-platform"}},
        "no label": {**owned_labels(), f"{project}_valkey_data": {}},
        "other poc project": {**owned_labels(), f"{project}_objects": {"com.docker.compose.project": "ai-platform-poc-other"}},
    }
    for label, labels in scenarios.items():
        docker = VolumeDocker(labels)
        context = lifecycle.load_context(tmp_path, "demo", runner=docker, environ={"PATH": "/usr/bin"})
        with pytest.raises(PocError, match="volume"):
            lifecycle.RealBackend(context).destroy(lifecycle.DownProof("demo", SNAPSHOT, MANIFEST_SHA))
        assert docker.removed == [], label
    bind = VolumeDocker(owned_labels(), options={f"{project}_objects": {"type": "none", "o": "bind", "device": "/home"}})
    context = lifecycle.load_context(tmp_path, "demo", runner=bind, environ={"PATH": "/usr/bin"})
    with pytest.raises(PocError, match="volume"):
        lifecycle.RealBackend(context).destroy(lifecycle.DownProof("demo", SNAPSHOT, MANIFEST_SHA))
    assert bind.removed == []


def test_destroy_fails_on_a_failed_or_ineffective_volume_removal(tmp_path):
    """Fix round 1: `down` must not report success while any runtime volume is still there."""
    make_stack(tmp_path)
    project = "ai-platform-poc-demo"
    for label, kwargs in {"rm fails": dict(fail_rm={f"{project}_pgdata_trixie"}),
                          "rm claims success, volume stays": dict(ghost={f"{project}_valkey_data"})}.items():
        docker = VolumeDocker(owned_labels(), **kwargs)
        context = lifecycle.load_context(tmp_path, "demo", runner=docker, environ={"PATH": "/usr/bin"})
        with pytest.raises(PocError, match="volume"):
            lifecycle.RealBackend(context).destroy(lifecycle.DownProof("demo", SNAPSHOT, MANIFEST_SHA))
        assert sorted(docker.removed) == sorted(owned_labels()), label  # every volume was still attempted
    clean = VolumeDocker(owned_labels())
    context = lifecycle.load_context(tmp_path, "demo", runner=clean, environ={"PATH": "/usr/bin"})
    lifecycle.RealBackend(context).destroy(lifecycle.DownProof("demo", SNAPSHOT, MANIFEST_SHA))
    assert clean.labels == {}

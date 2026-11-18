"""WP3 fix round 1 (CRITICAL): a failed restore is a durable, resumable state and never lets `up` start an empty stack.

`restore-pending.json` is written before any runtime volume exists and cleared only after the restore verified, before
api and worker start. While it is present `up` resumes (stop, remove this stack's partial runtime volumes by exact name,
restore again from the SAME snapshot) and never runs the normal path (alembic on an empty database). `backup` refuses.
A fake engine records the order of every step; the restic and database details are stubbed at the module seams.
"""
import hashlib
import json
import os
import stat
import threading
import time
from datetime import datetime, timezone

import pytest

from scripts.poc_backup import catalog, restore, verify
from scripts.poc_backup.model import BackupRef, DbState
from scripts.poc_backup.restic import Restic, private_dir
from scripts.poc_lib import lifecycle
from scripts.poc_lib import up as poc_up
from scripts.poc_lib.runner import CommandError, Result
from scripts.poc_lib.up import PocError
from tests.unit.test_poc_up import FakeRunner, _resolver, make_repo


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


PENDING = "restore-pending.json"
SNAPSHOT = "ab12cd34" * 8
ENV = {"PATH": "/usr/bin", "HOME": "/home/x"}
STATE = {"schema_head": "0011", "counts": {"tenants": 1, "jobs": 2}, "heads": [["t1", 3, "a" * 64]],
         "checkpoints": [["t1", 0, "b" * 64, "genesis"]], "objects": []}
MANIFEST = {**STATE, "version": 1, "stack": "demo", "created_at": "2026-11-17T12:00:00+00:00", "objects": [],
            "cost_counters": {"date": "2026-11-17", "counters": {}}}
RAW = (json.dumps(MANIFEST, sort_keys=True) + "\n").encode()
DIGEST = hashlib.sha256(RAW).hexdigest()
REF = BackupRef(stack="demo", snapshot_id=SNAPSHOT, manifest_sha256=DIGEST,
                created_at=datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc),
                state=DbState.from_mapping({**STATE, "objects": []}))
PROJECT = "ai-platform-poc-demo"
VOLUMES = [f"{PROJECT}_{name}" for name in ("objects", "pgdata_trixie", "valkey_data")]


class RestoreRunner(FakeRunner):
    """The WP1 fake engine plus volume state and an ordered event log. Records whether the pending file existed at the
    moment each important step ran."""

    def __init__(self, repo, **kwargs):
        super().__init__(**kwargs)
        self.repo = repo
        self.volumes: set[str] = set()
        self.events: list[tuple] = []
        self.fail_rm: set[str] = set()

    def _pending(self) -> bool:
        return (self.repo / ".poc/demo" / PENDING).exists()

    def run(self, argv, *, env=None, input=None, check=True, timeout=None, output_file=None, input_file=None):
        argv = list(argv)
        if argv[:3] == ["docker", "volume", "inspect"]:
            name = argv[-1]
            if name not in self.volumes:
                return Result(1, b"", b"no such volume")
            info = {"Name": name, "Driver": "local", "Options": None, "Labels": {"com.docker.compose.project": PROJECT}}
            return Result(0, json.dumps([info]).encode())
        if argv[:3] == ["docker", "volume", "rm"]:
            self.events.append(("rm", argv[-1]))
            if argv[-1] in self.fail_rm:
                return self._fail(argv, check)
            self.volumes.discard(argv[-1])
            return Result(0)
        if argv[:2] == ["docker", "compose"]:
            last_file = max(i for i, a in enumerate(argv) if a == "-f")
            tail = argv[last_file + 2:]  # everything after the three `-f <file>` options
            verb = next((a for a in tail if a in ("up", "stop", "down", "build", "ps", "exec", "run")), None)
            if verb == "up" and "postgres" in argv:
                self.events.append(("infra_up", self._pending()))
                self.volumes |= set(VOLUMES)
            elif verb == "up" and "api" in argv:
                self.events.append(("writers_up", self._pending()))
            elif verb == "stop":
                self.events.append(("stop", tuple(a for a in argv[-2:])))
            elif verb == "down":
                self.events.append(("down",))
            elif "alembic" in argv and "upgrade" in argv:
                self.events.append(("alembic", self._pending()))
            elif "alembic" in argv and "heads" in argv:
                return Result(0, b"0011\n")
            elif "pg_restore" in argv:
                self.events.append(("pg_restore",))
            elif "psql" in argv:
                sql = (input or b"").decode()
                if "pg_tables" in sql:
                    return Result(0, b"0\n")
                if "json_build_object" in sql:
                    return Result(0, json.dumps(STATE).encode())
            return super().run(argv, env=env, input=input, check=check, timeout=timeout)  # ps rows, git, image inspect
        return super().run(argv, env=env, input=input, check=check, timeout=timeout)

    @staticmethod
    def _fail(argv, check):
        if check:
            raise CommandError(argv, 1, b"boom")
        return Result(1, b"", b"boom")

    def names(self, kind):
        return [e for e in self.events if e[0] == kind]


def _stub_repository(monkeypatch, *, snapshots=None):
    """The repository holds exactly one snapshot, SNAPSHOT, whose manifest hashes to DIGEST."""
    rows = [{"id": SNAPSHOT, "time": "2026-11-17T12:00:00Z", "tags": ["poc", "stack-demo", f"manifest-{DIGEST}"]}] \
        if snapshots is None else snapshots
    monkeypatch.setattr(catalog, "latest_ref", lambda context: REF)
    monkeypatch.setattr(Restic, "snapshots", lambda self: rows)
    monkeypatch.setattr(catalog, "read_manifest_from_snapshot", lambda context, sid: (json.loads(RAW), DIGEST))

    def fake_restore(self, ref):
        private_dir(self.restore_dir, fresh=True)
        (self.restore_dir / "staging").mkdir()
        (self.restore_dir / "staging" / "manifest.json").write_bytes(RAW)
        (self.restore_dir / "staging" / "dump.pgc").write_bytes(b"PGDMP")
        return self.restore_dir / "staging"

    monkeypatch.setattr(Restic, "restore", fake_restore)
    monkeypatch.setattr(verify, "verify_restore_set", lambda *a, **k: None)
    monkeypatch.setattr(restore, "schema_head_of_release", lambda context: "0011")


def _after_down(repo, monkeypatch, **kwargs):
    """A stack that was up, was backed up and was taken down: marker, secrets, release manifest and pointer stay."""
    runner = RestoreRunner(repo, **kwargs)
    poc_up.up(repo, "demo", runner=runner, resolver=_resolver, port_picker=lambda: 18321, platform="linux/amd64",
              environ=ENV)
    (repo / ".poc/demo/latest.json").write_text(json.dumps(
        {"snapshot_id": SNAPSHOT, "manifest_sha256": DIGEST, "stack": "demo", "created_at": "2026-11-17T12:00:00+00:00"}))
    runner.volumes.clear()
    runner.events.clear()
    runner.calls.clear()
    _stub_repository(monkeypatch)
    return runner


def _up(repo, runner):
    return poc_up.up(repo, "demo", runner=runner, resolver=_resolver, port_picker=lambda: 19999,
                     platform="linux/amd64", environ=ENV)


def _fail(name):
    def raiser(*args, **kwargs):
        raise PocError(f"injected failure in {name}")
    return raiser


INJECTIONS = {
    "load_into_empty_database": lambda m: m.setattr(restore, "load_into_empty_database", _fail("load_into_empty_database")),
    "compare_state": lambda m: m.setattr(verify, "compare_state", _fail("compare_state")),
    "copy_objects": lambda m: m.setattr(restore, "copy_objects", _fail("copy_objects")),
}


# --- the marker itself -------------------------------------------------------------------------------------------------

def test_pending_marker_is_written_atomically_and_privately(tmp_path, monkeypatch):
    from scripts.poc_backup import pending
    folder = tmp_path / "stack"
    folder.mkdir(mode=0o700)
    synced, replaced = [], []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd))[1])
    monkeypatch.setattr(os, "replace", lambda a, b: (replaced.append((a, b)), real_replace(a, b))[1])
    pending.write_pending(folder, SNAPSHOT, DIGEST)
    path = folder / PENDING
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["snapshot_id"] == SNAPSHOT and json.loads(path.read_text())["manifest_sha256"] == DIGEST
    assert synced, "the marker must be flushed to disk before it is renamed into place"
    assert replaced and replaced[0][1] == path
    assert [p.name for p in folder.iterdir()] == [PENDING]  # no temporary file is left behind
    assert pending.read_pending(folder) == {"snapshot_id": SNAPSHOT, "manifest_sha256": DIGEST, "version": 1}
    pending.clear_pending(folder)
    assert pending.read_pending(folder) is None and not path.exists()


@pytest.mark.parametrize("content", ["{", "[]", '{"snapshot_id": "x"}', '{"snapshot_id": "zz", "manifest_sha256": "yy", "version": 1}'])
def test_unreadable_pending_marker_refuses_instead_of_being_ignored(tmp_path, content):
    from scripts.poc_backup import pending
    (tmp_path / PENDING).write_text(content)
    (tmp_path / PENDING).chmod(0o600)
    with pytest.raises(PocError, match="pending"):
        pending.read_pending(tmp_path)


def test_unsafe_pending_marker_refuses(tmp_path):
    from scripts.poc_backup import pending
    path = tmp_path / PENDING
    path.write_text(json.dumps({"snapshot_id": SNAPSHOT, "manifest_sha256": DIGEST, "version": 1}))
    path.chmod(0o644)
    with pytest.raises(PocError, match="pending"):
        pending.read_pending(tmp_path)


# --- a failure at any step keeps the marker and the next `up` resumes ------------------------------------------------

@pytest.mark.parametrize("target", sorted(INJECTIONS))
def test_failed_restore_keeps_marker_and_up_resumes_without_the_normal_path(repo, monkeypatch, target):
    runner = _after_down(repo, monkeypatch)
    folder = repo / ".poc/demo"
    with monkeypatch.context() as patch:
        INJECTIONS[target](patch)
        with pytest.raises(PocError, match="injected failure"):
            _up(repo, runner)
    assert (folder / PENDING).is_file(), "a failed restore must leave the marker"
    body = json.loads((folder / PENDING).read_text())
    assert body["snapshot_id"] == SNAPSHOT and body["manifest_sha256"] == DIGEST
    assert stat.S_IMODE((folder / PENDING).stat().st_mode) == 0o600
    # The marker existed before the volumes were created, and no writer and no migration ran on the partial data.
    assert runner.names("infra_up") == [("infra_up", True)]
    assert runner.names("writers_up") == [] and runner.names("alembic") == []

    runner.events.clear()
    marker = _up(repo, runner)  # the re-run resumes
    assert marker["project"] == PROJECT
    assert runner.names("alembic") == [], "a resume must never run the normal path (alembic on an empty database)"
    kinds = [e[0] for e in runner.events]
    assert kinds.index("stop") < kinds.index("down") < kinds.index("rm") < kinds.index("infra_up") < kinds.index("writers_up")
    assert runner.names("stop") == [("stop", ("api", "worker"))]
    assert [e[1] for e in runner.names("rm")] == VOLUMES  # exact names, this stack only, in marker order
    assert runner.names("infra_up") == [("infra_up", True)] and runner.names("pg_restore") == [("pg_restore",)]
    assert runner.names("writers_up") == [("writers_up", False)], "the marker is cleared before api and worker start"
    assert not (folder / PENDING).exists()
    assert json.loads((folder / "restore-report.json").read_text())["snapshot_id"] == SNAPSHOT


def test_resume_restores_the_snapshot_named_in_the_marker_not_a_newer_latest(repo, monkeypatch):
    runner = _after_down(repo, monkeypatch)
    with monkeypatch.context() as patch:
        INJECTIONS["copy_objects"](patch)
        with pytest.raises(PocError):
            _up(repo, runner)
    newer = BackupRef(stack="demo", snapshot_id="ff" * 32, manifest_sha256="ee" * 32, created_at=REF.created_at, state=REF.state)
    monkeypatch.setattr(catalog, "latest_ref", lambda context: newer)  # `latest` must not be consulted on a resume
    _up(repo, runner)
    assert json.loads((repo / ".poc/demo/restore-report.json").read_text())["snapshot_id"] == SNAPSHOT


def test_resume_refuses_when_the_snapshot_in_the_marker_is_missing_and_removes_nothing(repo, monkeypatch):
    runner = _after_down(repo, monkeypatch)
    with monkeypatch.context() as patch:
        INJECTIONS["load_into_empty_database"](patch)
        with pytest.raises(PocError):
            _up(repo, runner)
    runner.events.clear()
    _stub_repository(monkeypatch, snapshots=[])  # the repository no longer holds the snapshot
    with pytest.raises(PocError, match="snapshot.*(missing|not found)|(missing|not found).*snapshot"):
        _up(repo, runner)
    assert runner.names("rm") == [] and runner.names("infra_up") == [] and runner.names("alembic") == []
    assert (repo / ".poc/demo" / PENDING).is_file()
    unreadable = [{"id": SNAPSHOT, "time": "2026-11-17T12:00:00Z", "tags": ["poc", "stack-demo", "manifest-" + "0" * 64]}]
    _stub_repository(monkeypatch, snapshots=unreadable)  # present, but its manifest does not match the marker's digest
    monkeypatch.setattr(catalog, "read_manifest_from_snapshot", lambda context, sid: (json.loads(RAW), "0" * 64))
    with pytest.raises(PocError, match="digest|changed|snapshot"):
        _up(repo, runner)
    assert runner.names("rm") == [] and runner.names("alembic") == []


def test_garbage_marker_never_falls_back_to_the_normal_path(repo, monkeypatch):
    runner = _after_down(repo, monkeypatch)
    (repo / ".poc/demo" / PENDING).write_text("{")
    (repo / ".poc/demo" / PENDING).chmod(0o600)
    with pytest.raises(PocError, match="pending"):
        _up(repo, runner)
    assert runner.names("alembic") == [] and runner.names("infra_up") == [] and runner.names("rm") == []


def test_a_clean_restore_leaves_no_marker_and_a_repeat_up_is_normal(repo, monkeypatch):
    runner = _after_down(repo, monkeypatch)
    _up(repo, runner)
    assert not (repo / ".poc/demo" / PENDING).exists()
    assert runner.names("alembic") == []  # restored data is never migrated by the normal path
    runner.events.clear()
    _up(repo, runner)  # all volumes are present: an ordinary idempotent up
    assert runner.names("rm") == [] and runner.names("pg_restore") == []


def test_resume_removal_failure_stops_before_restoring(repo, monkeypatch):
    runner = _after_down(repo, monkeypatch)
    with monkeypatch.context() as patch:
        INJECTIONS["compare_state"](patch)
        with pytest.raises(PocError):
            _up(repo, runner)
    runner.events.clear()
    runner.fail_rm = {VOLUMES[1]}
    with pytest.raises(PocError, match="volume"):
        _up(repo, runner)
    assert runner.names("pg_restore") == [] and runner.names("alembic") == [] and runner.names("writers_up") == []
    assert (repo / ".poc/demo" / PENDING).is_file()


# --- backup and down never run beside a pending restore --------------------------------------------------------------

def test_backup_and_down_refuse_while_a_restore_is_pending(repo, monkeypatch):
    runner = _after_down(repo, monkeypatch)
    with monkeypatch.context() as patch:
        INJECTIONS["copy_objects"](patch)
        with pytest.raises(PocError):
            _up(repo, runner)
    pointer = (repo / ".poc/demo/latest.json").read_text()
    runner.calls.clear()
    with pytest.raises(PocError, match="restore is pending"):
        lifecycle.backup(repo, "demo", runner=runner, environ=ENV)
    with pytest.raises(PocError, match="restore is pending"):
        lifecycle.down(repo, "demo", runner=runner, environ={**ENV, "POC_RECOVERY_REF": SNAPSHOT})
    assert not any(c.argv[:2] == ["docker", "compose"] for c in runner.calls)  # nothing was started, stopped or dumped
    assert (repo / ".poc/demo/latest.json").read_text() == pointer
    status = lifecycle.status(repo, "demo", runner=runner, environ=ENV)
    assert status["restore_pending"] == {"snapshot_id": SNAPSHOT, "manifest_sha256": DIGEST}


# --- the decision to restore is made inside the stack lock -------------------------------------------------------------

def test_up_decides_restoring_after_a_concurrent_down_finishes(repo, monkeypatch):
    """`down` holds the stack lock; `up` waits for it. When `down` finishes (the volumes are gone) `up` must see the
    post-down state and restore, not act on what it saw before the lock."""
    runner = _after_down(repo, monkeypatch)
    runner.volumes |= set(VOLUMES)  # before `down`: the stack is up
    lock_path = repo / ".poc/.locks/demo.lock"
    import fcntl
    lock_path.parent.mkdir(mode=0o700, exist_ok=True)
    held = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    outcome = {}

    def run_up():
        try:
            outcome["marker"] = _up(repo, runner)
        except BaseException as exc:  # noqa: BLE001
            outcome["error"] = exc

    thread = threading.Thread(target=run_up)
    thread.start()
    time.sleep(1.0)
    assert thread.is_alive(), "up must be waiting for the lock held by down"
    runner.volumes.clear()  # down completes ...
    runner.events.clear()
    fcntl.flock(held, fcntl.LOCK_UN)
    os.close(held)  # ... and releases the lock
    thread.join(30)
    assert "error" not in outcome, outcome.get("error")
    assert runner.names("alembic") == [], "up acted on the pre-lock volume state and migrated an empty database"
    assert runner.names("pg_restore") == [("pg_restore",)]
    assert runner.names("writers_up") == [("writers_up", False)]

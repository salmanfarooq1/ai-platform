"""WP3: the backup pipeline and the restic service, with a fake Docker engine (no containers needed)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from scripts.poc_lib import lifecycle
from scripts.poc_lib import up as poc_up
from scripts.poc_lib.keys import ensure_stack_secrets
from scripts.poc_lib.runner import CommandError, Result
from scripts.poc_lib.up import PocError

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
SNAPSHOT = "9f" * 32
OBJECT = b"hello object"
OBJECT_KEY = hashlib.sha256(OBJECT).hexdigest()
TENANT = "11111111-1111-1111-1111-111111111111"
STATE = {"schema_head": "0011", "counts": {"tenants": 1, "jobs": 2, "alembic_version": 1},
         "heads": [[TENANT, 3, "a" * 64]], "checkpoints": [[TENANT, 0, "b" * 64, "genesis"]], "objects": [OBJECT_KEY]}


# --- restic service contract -----------------------------------------------------------------------------------------

def _compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_restic_service_contract():
    compose = _compose()
    restic = compose["services"]["restic"]
    assert restic["profiles"] == ["backup"]  # never part of the default four services
    assert restic["build"]["context"] == "docker/restic"
    assert restic["entrypoint"] == ["/restic"]
    assert restic.get("read_only") is True and restic["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in restic["security_opt"]
    volumes = [v if isinstance(v, str) else v["target"] for v in restic["volumes"]]
    text = json.dumps(restic)
    assert "/run/secrets/restic-password" in text and "RESTIC_PASSWORD_FILE" in text  # a file, never the value
    assert not any(v.startswith("/var/run/docker.sock") or "docker.sock" in v for v in map(str, restic["volumes"]))
    assert any("/repo" in v for v in volumes) and any("/staging" in v for v in volumes)
    staging = next(v for v in restic["volumes"] if "/staging" in str(v))
    assert str(staging).endswith(":ro") or (isinstance(staging, dict) and staging.get("read_only"))
    for forbidden in ("RESTIC_PASSWORD:", "RESTIC_PASSWORD=", "rclone"):
        assert forbidden not in text
    sources = "".join(p.read_text() for p in (ROOT / "scripts/poc_backup").glob("*.py"))
    assert "rclone" not in sources and "docker.sock" not in sources
    assert set(compose["services"]) - {"restic"} >= {"postgres", "valkey", "api", "worker"}
    # One tagged backup of one staged folder: the argv builder used by the pipeline.
    from scripts.poc_backup import restic
    argv = restic.backup_args("demo", "d" * 64)
    assert argv[0] == "backup" and argv.count("/staging") == 1
    assert "--tag" in argv and "manifest-" + "d" * 64 in argv and "stack-demo" in argv
    assert not any(a.startswith("--password") for a in argv)


# --- fake engine -----------------------------------------------------------------------------------------------------

BACKEND_PID = 4242


class Session:
    """The long-lived `psql` of the backup lock: it prints the backend pid, then LOCKED (fix round 1: the lock is proven)."""

    def __init__(self, owner):
        self.owner, self.closed, self.sent = owner, False, b""
        self.lines = [str(BACKEND_PID), "LOCKED"]

    def write(self, data):
        self.sent += data

    def readline(self, timeout=None):
        if self.owner.fail == "lock":
            raise PocError("could not take the backup lock")
        if self.owner.fail == "lock_timeout":
            raise TimeoutError("no output from the child process in time")
        return self.lines.pop(0)

    def close(self):
        self.closed = True
        self.owner.events.append("lock_released")

    def poll(self):
        if self.closed:
            return 0
        if self.owner.fail == "psql_died" and "pg_dump" in self.owner.events:
            return 137  # the client process is gone
        return None


class FakeDocker:
    def __init__(self, root, fail=None):
        self.root, self.fail = root, fail
        self.events, self.calls, self.sessions = [], [], []
        self.restic_backups = []
        self.staged_at_backup = None
        self.dump_seen = None
        self.lock_queries = []
        self.scans = []

    # Tracks the compose argument that names the service container the command runs in.
    def spawn(self, argv, *, env=None):
        self.calls.append(list(argv))
        self.events.append("lock_taken")
        session = Session(self)
        self.sessions.append(session)
        return session

    def run(self, argv, *, env=None, input=None, check=True, timeout=None, output_file=None, input_file=None):
        argv = list(argv)
        self.calls.append(argv)
        result = self._route(argv, input, output_file, input_file)
        if check and result.returncode != 0:
            raise CommandError(argv, result.returncode, result.stderr)
        return result

    def _write(self, output_file, data):
        if output_file is not None:
            Path(output_file).write_bytes(data)

    def _route(self, argv, input, output_file, input_file):
        if argv[:3] == ["docker", "context", "show"]:
            return Result(0, b"default\n")
        if "pg_dump" in argv:
            self.events.append("pg_dump")
            if self.fail == "cancel":
                raise KeyboardInterrupt
            self._write(output_file, b"PGDMP-partial" if self.fail == "dump" else b"PGDMP-complete")
            return Result(1 if self.fail == "dump" else 0, b"", b"pg_dump: error")
        if "pg_restore" in argv:
            return Result(0)
        if "psql" in argv:
            sql = (input or b"").decode()
            if "json_build_object" in sql:
                return Result(0, json.dumps(STATE).encode())
            if "pg_locks" in sql:
                self.events.append("lock_checked")
                self.lock_queries.append(sql)
                return Result(0, b"0\n" if self.fail == "lock_lost" else b"1\n")
            return Result(0)
        if "valkey-cli" in argv:
            if "--scan" in argv:
                self.scans.append(argv[argv.index("--pattern") + 1])
                return Result(0, f"cost:{TENANT}:2026-11-17\n".encode())
            if "GET" in argv:
                return Result(0, b"1250000\n")
        if "cat" in argv and "api" in argv:
            self._write(output_file, OBJECT)
            return Result(0)
        if "restic" in argv:
            return self._restic(argv[argv.index("restic") + 1:], output_file)
        return Result(0)

    def _restic(self, args, output_file):
        verb = args[0]
        if verb == "backup":
            self.events.append("restic_backup")
            self.restic_backups.append(args)
            staging = self.root / ".poc/demo/staging"
            self.staged_at_backup = sorted(p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file())
            self.manifest_bytes = (staging / "manifest.json").read_bytes()
            if self.fail == "restic":
                return Result(1, b"", b"repository is locked")
            summary = json.dumps({"message_type": "summary", "snapshot_id": SNAPSHOT}).encode()
            return Result(0, b'{"message_type":"status"}\n' + summary + b"\n")
        if verb == "snapshots":
            manifest_sha = hashlib.sha256(self.manifest_bytes).hexdigest()
            row = {"id": SNAPSHOT, "short_id": SNAPSHOT[:8], "time": "2026-11-17T12:00:00Z",
                   "tags": ["poc", "stack-demo", f"manifest-{manifest_sha}"]}
            return Result(0, json.dumps([row]).encode())
        if verb == "dump":
            self._write(output_file, self.manifest_bytes)
            return Result(0)
        return Result(0)  # cat config, init, check


@pytest.fixture
def stack(tmp_path):
    ensure_stack_secrets(tmp_path, "demo")
    folder = tmp_path / ".poc" / "demo"
    marker = poc_up._expected_marker("demo", 18321)
    poc_up._write_private(folder / "marker.json", json.dumps(marker, sort_keys=True) + "\n", replace=False)
    (folder / "release-manifest.json").write_text('{"release": "test"}\n')
    return tmp_path


def run_backup(stack, docker):
    return lifecycle.backup(stack, "demo", runner=docker, environ={"PATH": "/usr/bin"}, clock=lambda: NOW)


def test_backup_stages_one_snapshot_and_publishes_last(stack):
    docker = FakeDocker(stack)
    ref = run_backup(stack, docker)
    assert docker.events.index("lock_released") < docker.events.index("restic_backup")  # the lock covers capture only
    assert docker.events.index("pg_dump") > docker.events.index("lock_taken")
    assert len(docker.restic_backups) == 1  # one snapshot, not two linked ones
    assert docker.staged_at_backup is not None
    assert docker.staged_at_backup == ["dump.pgc", f"objects/{OBJECT_KEY}", "manifest.json"] or \
        sorted(docker.staged_at_backup) == sorted(["dump.pgc", f"objects/{OBJECT_KEY}", "manifest.json"])
    manifest = json.loads(docker.manifest_bytes)
    assert manifest["version"] == 1 and manifest["stack"] == "demo"
    assert manifest["dump"]["sha256"] == hashlib.sha256(b"PGDMP-complete").hexdigest()
    assert manifest["objects"] == [{"key": OBJECT_KEY, "sha256": OBJECT_KEY, "size": len(OBJECT)}]
    assert manifest["counts"] == STATE["counts"] and manifest["schema_head"] == "0011"
    assert manifest["signing"].keys() == {"key_id", "public_key"}
    assert manifest["cost_counters"] == {"date": "2026-11-17", "counters": {f"cost:{TENANT}:2026-11-17": 1250000}}
    assert manifest["release_manifest_sha256"] == hashlib.sha256(b'{"release": "test"}\n').hexdigest()
    private = (stack / ".poc/demo/receipt-signing.key").read_text().strip()
    password = (stack / ".poc/demo/restic-password").read_text().strip()
    assert private not in docker.manifest_bytes.decode() and password not in docker.manifest_bytes.decode()
    for call in docker.calls:
        assert private not in " ".join(call) and password not in " ".join(call)
    pointer = json.loads((stack / ".poc/demo/latest.json").read_text())
    assert pointer["snapshot_id"] == SNAPSHOT == ref.snapshot_id
    assert pointer["manifest_sha256"] == hashlib.sha256(docker.manifest_bytes).hexdigest() == ref.manifest_sha256
    assert not (stack / ".poc/demo/staging").exists() or not any((stack / ".poc/demo/staging").iterdir())
    assert docker.sessions[0].closed
    tag = [a for a in docker.restic_backups[0] if a.startswith("manifest-")]
    assert tag == [f"manifest-{ref.manifest_sha256}"]


@pytest.mark.parametrize("failure", ["dump", "restic", "cancel", "lock"])
def test_failed_dump_command_never_publishes_backup(stack, failure):
    pointer = stack / ".poc/demo/latest.json"
    previous = json.dumps({"snapshot_id": "e" * 64, "manifest_sha256": "f" * 64, "stack": "demo",
                           "created_at": "2026-11-16T00:00:00+00:00"})
    pointer.write_text(previous)
    docker = FakeDocker(stack, fail=failure)
    with pytest.raises((PocError, CommandError, KeyboardInterrupt)):
        run_backup(stack, docker)
    assert pointer.read_text() == previous  # latest never moves
    if docker.sessions:
        assert all(s.closed for s in docker.sessions)  # the lock is released on every failure path
    staging = stack / ".poc/demo/staging"
    assert not staging.exists() or not any(staging.iterdir())  # the partial dump is gone
    if failure in ("dump", "cancel", "lock"):
        assert docker.restic_backups == []  # nothing reaches the repository
    if failure == "restic":
        assert docker.restic_backups  # it was tried; the failure was not ignored


def test_cost_counters_are_reapplied_only_on_the_same_utc_day():
    from scripts.poc_backup.restore import counters_to_apply
    manifest = {"cost_counters": {"date": "2026-11-17", "counters": {f"cost:{TENANT}:2026-11-17": 1250000, "cost:x:2026-11-17": 0}}}
    assert counters_to_apply(manifest, "2026-11-17") == {f"cost:{TENANT}:2026-11-17": 1250000}
    assert counters_to_apply(manifest, "2026-11-18") == {}  # a later day starts a new counter
    assert counters_to_apply({}, "2026-11-17") == {}


# --- fix round 1: the backup proves it still holds its lock ------------------------------------------------------------

def test_backup_proves_the_lock_by_pid_and_key_before_it_finishes(stack):
    from core.database.locks import BACKUP_LOCK_KEY
    docker = FakeDocker(stack)
    run_backup(stack, docker)
    assert "lock_checked" in docker.events
    assert docker.events.index("pg_dump") < docker.events.index("lock_checked") < docker.events.index("lock_released") \
        < docker.events.index("restic_backup")
    sql = docker.lock_queries[0]
    assert "pg_locks" in sql and str(BACKEND_PID) in sql  # the lock session's pid
    assert str(BACKUP_LOCK_KEY >> 32) in sql and str(BACKUP_LOCK_KEY & 0xFFFFFFFF) in sql  # the advisory key (classid, objid)
    assert "mode = 'ExclusiveLock'" in sql  # a shared (purge) hold of the same key is not the backup's exclusive lock


@pytest.mark.parametrize("failure", ["lock_lost", "psql_died"])
def test_backup_fails_when_the_lock_is_no_longer_held(stack, failure):
    pointer = stack / ".poc/demo/latest.json"
    previous = json.dumps({"snapshot_id": "e" * 64, "manifest_sha256": "f" * 64, "stack": "demo",
                           "created_at": "2026-11-16T00:00:00+00:00"})
    pointer.write_text(previous)
    docker = FakeDocker(stack, fail=failure)
    with pytest.raises(PocError, match="lock"):
        run_backup(stack, docker)
    assert pointer.read_text() == previous  # latest.json (the snapshot pointer) did not move
    assert docker.restic_backups == []  # no snapshot was stored
    assert all(s.closed for s in docker.sessions)
    assert not (stack / ".poc/demo/staging").exists() or not any((stack / ".poc/demo/staging").iterdir())


def test_a_lock_wait_timeout_is_a_clean_error_not_a_traceback(stack):
    docker = FakeDocker(stack, fail="lock_timeout")
    with pytest.raises(PocError, match="backup lock"):
        run_backup(stack, docker)  # TimeoutError from the line reader becomes the same clean refusal
    assert docker.restic_backups == [] and all(s.closed for s in docker.sessions)
    assert not (stack / ".poc/demo/latest.json").exists()


# --- fix round 1: UTC midnight and the daily cost counters (R4 INCRBY) -------------------------------------------------

class CountersContext:
    """A context with a fake Valkey that supports GET, INCRBY and EXPIRE; the restore steps themselves are stubbed."""

    def __init__(self, stack_dir, valkey=None):
        self.stack_dir = stack_dir
        self.store = dict(valkey or {})
        self.commands = []

    def valkey(self, *args):
        self.commands.append(args)
        if args[0] == "GET":
            return f"{self.store[args[1]]}\n" if args[1] in self.store else "\n"
        if args[0] == "INCRBY":
            self.store[args[1]] = self.store.get(args[1], 0) + int(args[2])
            return f"{self.store[args[1]]}\n"
        return "1\n"


COST_KEY = f"cost:{TENANT}:2026-11-17"
COST_MANIFEST = {"schema_head": "0011", "objects": [], "cost_counters": {"date": "2026-11-17", "counters": {COST_KEY: 1250000}},
                 "counts": STATE["counts"], "heads": STATE["heads"], "checkpoints": STATE["checkpoints"]}


def _restore_with_clock(monkeypatch, tmp_path, context, start, finish):
    """Run `restore_latest` with a clock that is `start` until the restore does its work, then `finish` (the restore
    crossed midnight while it copied objects)."""
    from scripts.poc_backup import restore, verify
    from scripts.poc_backup.model import BackupRef, DbState
    now = {"value": start}
    raw = (json.dumps(COST_MANIFEST, sort_keys=True) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    ref = BackupRef("demo", SNAPSHOT, digest, start, DbState.from_mapping({**COST_MANIFEST, "objects": []}))

    def fake_restore(self, backup_ref):
        directory = self.restore_dir / "staging"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "manifest.json").write_bytes(raw)
        return directory

    from scripts.poc_backup.restic import Restic
    monkeypatch.setattr(Restic, "restore", fake_restore)
    monkeypatch.setattr(verify, "verify_restore_set", lambda *a, **k: None)
    monkeypatch.setattr(restore, "schema_head_of_release", lambda c: "0011")
    monkeypatch.setattr(restore, "load_into_empty_database", lambda c, d, m: DbState.from_mapping({**COST_MANIFEST, "objects": []}))

    def slow_copy(c, d, m):
        now["value"] = finish  # the object copy took long enough to cross midnight
        return 0

    monkeypatch.setattr(restore, "copy_objects", slow_copy)
    return restore.restore_latest(context, clock=lambda: now["value"], ref=ref)


def test_restore_that_crosses_utc_midnight_applies_the_counters_exactly_once(monkeypatch, tmp_path):
    start = datetime(2026, 11, 17, 23, 59, 40, tzinfo=timezone.utc)
    finish = datetime(2026, 11, 18, 0, 0, 20, tzinfo=timezone.utc)
    context = CountersContext(tmp_path)
    report = _restore_with_clock(monkeypatch, tmp_path, context, start, finish)
    # The decision is made when the restore starts: a restore begun on the manifest's UTC day never loses its counters.
    assert context.store == {COST_KEY: 1250000}
    assert report["cost_counters_restored"] == {COST_KEY: 1250000}
    # A resumed attempt against a Valkey that already holds them must not double-apply.
    again = _restore_with_clock(monkeypatch, tmp_path, context, start, finish)
    assert context.store == {COST_KEY: 1250000}, "applied twice"
    assert again["cost_counters_restored"] == {COST_KEY: 1250000}


def test_restore_that_starts_after_midnight_applies_no_old_counters(monkeypatch, tmp_path):
    start = datetime(2026, 11, 18, 0, 0, 5, tzinfo=timezone.utc)
    context = CountersContext(tmp_path)
    report = _restore_with_clock(monkeypatch, tmp_path, context, start, start)
    assert context.store == {} and report["cost_counters_restored"] == {}  # a new day starts a new counter


def test_a_later_attempt_tops_a_partial_counter_up_without_exceeding_it(monkeypatch, tmp_path):
    start = datetime(2026, 11, 17, 23, 0, 0, tzinfo=timezone.utc)
    context = CountersContext(tmp_path, {COST_KEY: 500000})  # a partly applied earlier attempt
    _restore_with_clock(monkeypatch, tmp_path, context, start, start)
    assert context.store == {COST_KEY: 1250000}
    context = CountersContext(tmp_path, {COST_KEY: 9000000})  # already higher (spend since): never lowered
    _restore_with_clock(monkeypatch, tmp_path, context, start, start)
    assert context.store == {COST_KEY: 9000000}


def test_backup_that_crosses_utc_midnight_keeps_the_counters_of_the_day_it_started(stack):
    """The manifest's counter date and the scanned keys both come from the instant the backup started."""
    ticks = iter([datetime(2026, 11, 17, 23, 59, 59, tzinfo=timezone.utc)] + [datetime(2026, 11, 18, 0, 0, 30, tzinfo=timezone.utc)] * 20)
    docker = FakeDocker(stack)
    lifecycle.backup(stack, "demo", runner=docker, environ={"PATH": "/usr/bin"}, clock=lambda: next(ticks))
    assert docker.scans == ["cost:*:2026-11-17"]
    assert json.loads(docker.manifest_bytes)["cost_counters"]["date"] == "2026-11-17"

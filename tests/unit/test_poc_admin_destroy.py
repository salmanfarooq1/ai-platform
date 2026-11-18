"""WP4 product gaps the M0 drill exposed, closed in the product (a second client needs each of them):

- `poc admin <stack> ...`: the identity and policy CLI against a stack whose Postgres is not published.
- `poc destroy <stack> --confirm <stack>`: the explicit, total end of a stack (the checked `down` keeps key and backups).
- `poc status --json` lists the backup's chain heads and checkpoints, so a restore can be compared with it.
"""
import json
import os
from pathlib import Path

import pytest

from scripts.poc_backup import catalog
from scripts.poc_lib import admin, lifecycle
from scripts.poc_lib.runner import CommandError, Result
from scripts.poc_lib.up import PocError
from tests.unit.test_poc import LocalDocker, NoCalls, VolumeDocker, make_stack, owned_labels, ref

PASSWORD = "owner-pw-sentinel-0451"
ENV = {"PATH": "/usr/bin", "POSTGRES_PASSWORD": PASSWORD}


class Recorder(LocalDocker):
    """Records the full call (argv, env, stdin) of every command and answers `create-key` like the real CLI."""

    def __init__(self, stdout=b"", fail=None):
        super().__init__()
        self.full = []
        self.stdout = stdout
        self.fail = fail

    def run(self, argv, *, env=None, input=None, check=True, **kwargs):
        argv = list(argv)
        self.full.append({"argv": argv, "env": dict(env or {}), "input": input})
        if argv[:3] == ["docker", "context", "show"]:
            return Result(0, b"default\n")
        if self.fail is not None and "run" in argv:
            raise self.fail
        return Result(0, self.stdout if "run" in argv else b"")

    def compose_runs(self):
        return [c for c in self.full if c["argv"][:2] == ["docker", "compose"] and "run" in c["argv"]]


def repo_with_identity(tmp_path):
    (tmp_path / "scripts" / "admin").mkdir(parents=True)
    (tmp_path / "scripts" / "admin" / "identity.py").write_text("# the operator CLI\n")
    make_stack(tmp_path)
    return tmp_path


# --- poc admin ---------------------------------------------------------------------------------------------------------

def test_admin_runs_the_identity_cli_in_the_api_image_with_no_secret_in_argv(tmp_path):
    root = repo_with_identity(tmp_path)
    runner = Recorder(stdout=b"principal x created: id=abc\n")
    result = admin.run(root, "demo", ["create-principal", "default", "service", "x"], runner=runner, environ=ENV)
    assert result == "principal x created: id=abc\n"
    (call,) = runner.compose_runs()
    argv = call["argv"]
    assert argv[argv.index("run") + 1:argv.index("run") + 5] == ["--rm", "--no-deps", "-T", "-e"]
    assert argv[argv.index("-e") + 1] == "MIGRATION_DATABASE_URL"  # by name; the value travels in the environment only
    assert PASSWORD not in " ".join(a for c in runner.full for a in c["argv"])
    assert PASSWORD in call["env"]["MIGRATION_DATABASE_URL"] and call["env"]["MIGRATION_DATABASE_URL"].startswith("postgresql://postgres:")
    mount = argv[argv.index("-v") + 1]
    assert mount == f"{root / 'scripts/admin/identity.py'}:/app/identity_admin.py:ro"  # one read-only file, nothing else
    assert argv[argv.index("api"):] == ["api", "python", "/app/identity_admin.py", "create-principal", "default", "service", "x"]


@pytest.mark.parametrize("args", [[], [""], ["bash"], ["-c", "id"], ["--dsn", "postgresql://x"], ["create-key", "--dsn=postgresql://x"],
                                  ["list-keys", "--dsn", "postgresql://x"], ["CREATE-KEY"], ["create-key\n"]])
def test_admin_allows_only_the_known_subcommands_and_never_a_dsn(tmp_path, args):
    root = repo_with_identity(tmp_path)
    runner = Recorder()
    with pytest.raises(PocError):
        admin.run(root, "demo", args, runner=runner, environ=ENV)
    assert runner.compose_runs() == []


def test_admin_reads_a_policy_from_stdin_when_the_file_argument_is_a_dash(tmp_path):
    root = repo_with_identity(tmp_path)
    runner = Recorder(stdout=b"policy version 3 is now active for tenant default\n")
    document = b'{"allowed_kbs": "*", "allowed_tools": "*", "allowed_models": "*"}'
    admin.run(root, "demo", ["set-policy", "default", "-"], runner=runner, environ=ENV, stdin=document)
    (call,) = runner.compose_runs()
    assert call["argv"][-3:] == ["set-policy", "default", "/dev/stdin"] and call["input"] == document
    with pytest.raises(PocError, match="stdin"):
        admin.run(root, "demo", ["set-policy", "default", "-"], runner=Recorder(), environ=ENV, stdin=None)


def test_admin_refuses_a_missing_marker_a_pending_restore_and_a_missing_cli_file(tmp_path):
    with pytest.raises(PocError, match="marker"):
        admin.run(tmp_path, "demo", ["list-keys"], runner=Recorder(), environ=ENV)
    root = repo_with_identity(tmp_path)
    (root / "scripts/admin/identity.py").unlink()
    with pytest.raises(PocError, match="identity"):
        admin.run(root, "demo", ["list-keys"], runner=Recorder(), environ=ENV)
    root = repo_with_identity(tmp_path / "second")
    (root / ".poc/demo/restore-pending.json").write_text(json.dumps({"snapshot_id": "a" * 64, "manifest_sha256": "b" * 64, "version": 1}))
    (root / ".poc/demo/restore-pending.json").chmod(0o600)
    runner = Recorder()
    with pytest.raises(PocError, match="restore is pending"):
        admin.run(root, "demo", ["list-keys"], runner=runner, environ=ENV)
    assert runner.compose_runs() == []


def test_admin_failure_shows_the_tool_message_without_the_database_password(tmp_path):
    root = repo_with_identity(tmp_path)
    failure = CommandError(["docker", "compose", "run"], 2,
                           f"error: could not connect to postgresql://postgres:{PASSWORD}@postgres:5432/rag_platform".encode())
    with pytest.raises(PocError) as raised:
        admin.run(root, "demo", ["list-keys"], runner=Recorder(fail=failure), environ=ENV)
    assert "could not connect" in str(raised.value) and PASSWORD not in str(raised.value)


# --- poc destroy -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("confirm", [None, "", "other", "DEMO", "demo ", "dem"])
def test_destroy_requires_the_exact_stack_name_as_confirmation(tmp_path, confirm):
    folder = make_stack(tmp_path)
    runner = NoCalls()
    with pytest.raises(PocError, match="confirm"):
        lifecycle.destroy(tmp_path, "demo", confirm=confirm, runner=runner, environ={"PATH": "/usr/bin"})
    assert runner.calls == [] and (folder / "marker.json").exists()


def test_destroy_removes_runtime_images_and_the_whole_stack_folder_and_nothing_else(tmp_path):
    folder = make_stack(tmp_path)
    (folder / "backups" / "data" / "00").mkdir(parents=True)
    pack = folder / "backups" / "data" / "00" / "pack"
    pack.write_text("encrypted")
    pack.chmod(0o400)  # restic writes read-only files
    other = make_stack(tmp_path, stack="other", port=18322)
    docker = VolumeDocker(owned_labels())
    lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"})
    assert not folder.exists() and (other / "marker.json").exists() and (other / "receipt-signing.key").exists()
    assert sorted(docker.removed) == sorted(owned_labels())
    compose = [c for c in docker.calls if c[:2] == ["docker", "compose"]]
    assert compose and all("--volumes" not in c and "-v" not in c for c in compose)
    assert ["docker", "image", "rm", "ai-platform-poc-demo-api"] in docker.calls
    assert ["docker", "image", "rm", "ai-platform-poc-demo-worker"] in docker.calls
    assert not any(c[:3] in (["docker", "system", "prune"], ["docker", "volume", "prune"]) for c in docker.calls)
    names = " ".join(a for c in docker.calls for a in c)
    assert "ai-platform_pgdata" not in names and "pgdata_trixie" not in names.replace("ai-platform-poc-demo_pgdata_trixie", "")


def test_destroy_refuses_a_foreign_volume_and_keeps_everything(tmp_path):
    folder = make_stack(tmp_path)
    project = "ai-platform-poc-demo"
    labels = {**owned_labels(), f"{project}_objects": {"com.docker.compose.project": "ai-platform"}}
    docker = VolumeDocker(labels)
    with pytest.raises(PocError, match="volume"):
        lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"})
    assert docker.removed == [] and (folder / "receipt-signing.key").exists() and (folder / "marker.json").exists()
    assert not any(c[:3] == ["docker", "image", "rm"] for c in docker.calls)


def test_destroy_keeps_the_folder_when_a_volume_cannot_be_removed(tmp_path):
    folder = make_stack(tmp_path)
    docker = VolumeDocker(owned_labels(), fail_rm={"ai-platform-poc-demo_objects"})
    with pytest.raises(PocError, match="volume"):
        lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"})
    assert (folder / "receipt-signing.key").exists()  # the key and the backups are the way back while data remains


def test_destroy_refuses_a_stack_without_marker_and_a_symlinked_or_foreign_folder(tmp_path):
    with pytest.raises(PocError, match="marker"):
        lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=LocalDocker(), environ={"PATH": "/usr/bin"})
    folder = make_stack(tmp_path)
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "keep.txt").write_text("mine")
    moved = tmp_path / "moved"
    folder.rename(moved)
    folder.symlink_to(moved)  # .poc/demo is now a symlink to another directory
    docker = VolumeDocker(owned_labels())
    with pytest.raises(PocError):
        lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"})
    assert docker.removed == [] and (moved / "marker.json").exists() and (precious / "keep.txt").exists()


def test_destroy_refuses_while_another_lifecycle_command_holds_the_lock(tmp_path):
    import fcntl

    folder = make_stack(tmp_path)
    (folder.parent / ".locks").mkdir(mode=0o700, exist_ok=True)
    held = os.open(folder.parent / ".locks" / (folder.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        docker = VolumeDocker(owned_labels())
        with pytest.raises(PocError, match="another lifecycle"):
            lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"})
        assert docker.removed == [] and (folder / "marker.json").exists()
    finally:
        os.close(held)


def test_destroy_may_abandon_a_pending_restore_because_the_operator_said_so_by_name(tmp_path):
    folder = make_stack(tmp_path)
    (folder / "restore-pending.json").write_text(json.dumps({"snapshot_id": "a" * 64, "manifest_sha256": "b" * 64, "version": 1}))
    (folder / "restore-pending.json").chmod(0o600)
    lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=VolumeDocker(owned_labels()), environ={"PATH": "/usr/bin"})
    assert not folder.exists()


# --- status lists the backup's heads and checkpoints ---------------------------------------------------------------------

def test_status_lists_the_latest_backups_heads_and_checkpoints(tmp_path, monkeypatch):
    make_stack(tmp_path)
    monkeypatch.setattr(catalog, "latest_ref", lambda context: ref())
    report = lifecycle.status(tmp_path, "demo", runner=Recorder(), environ={"PATH": "/usr/bin"})
    latest = report["latest_backup"]
    assert latest["heads"] == [["t1", 4, "a" * 64]] and latest["checkpoints"] == [["t1", 0, "b" * 64, "genesis"]]
    assert latest["counts"] == {"tenants": 1, "jobs": 3}
    assert Path(tmp_path / ".poc/demo/marker.json").exists()


def test_destroy_also_removes_the_scratch_upload_volume_but_only_if_it_is_ours(tmp_path):
    """Found by the live drill: the compose `app_tmp` volume is not in the marker's runtime list, so it was left behind."""
    project = "ai-platform-poc-demo"
    make_stack(tmp_path)
    docker = VolumeDocker({**owned_labels(), f"{project}_app_tmp": {"com.docker.compose.project": project}})
    lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"})
    assert f"{project}_app_tmp" in docker.removed and docker.labels == {}
    (tmp_path / "second").mkdir()
    other = make_stack(tmp_path / "second")
    foreign = VolumeDocker({**owned_labels(), f"{project}_app_tmp": {"com.docker.compose.project": "ai-platform"}})
    with pytest.raises(PocError, match="volume"):
        lifecycle.destroy(tmp_path / "second", "demo", confirm="demo", runner=foreign, environ={"PATH": "/usr/bin"})
    assert foreign.removed == [] and (other / "marker.json").exists()


def test_lifecycle_lock_is_outside_stack_directory(tmp_path):
    from scripts.poc_lib.context import lifecycle_lock

    stack_dir = tmp_path / '.poc' / 'fixture'
    stack_dir.mkdir(parents=True)
    stack_dir.parent.chmod(0o700)
    with lifecycle_lock(stack_dir):
        assert (tmp_path / '.poc' / '.locks' / 'fixture.lock').is_file()


TOKEN = "fedcba9876543210" * 2


def _owned(folder, token=TOKEN):
    path = folder / "owner.token"
    path.write_text(token + "\n")
    path.chmod(0o600)


def test_destroy_with_an_owner_token_only_removes_the_stack_that_carries_that_token(tmp_path):
    folder = make_stack(tmp_path)
    _owned(folder)
    docker = VolumeDocker(owned_labels())
    lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"}, owner_token=TOKEN)
    assert not folder.exists()


@pytest.mark.parametrize("token,written", [("0" * 32, TOKEN), (TOKEN, None)])
def test_destroy_refuses_a_stack_whose_owner_token_differs_or_is_missing(tmp_path, token, written):
    """A stack that existed before the drill (or belongs to another creator) is never destroyed by the drill."""
    folder = make_stack(tmp_path)
    if written:
        _owned(folder, written)
    docker = VolumeDocker(owned_labels())
    with pytest.raises(PocError, match="owner"):
        lifecycle.destroy(tmp_path, "demo", confirm="demo", runner=docker, environ={"PATH": "/usr/bin"}, owner_token=token)
    assert docker.removed == [] and (folder / "marker.json").exists() and (folder / "receipt-signing.key").exists()
    assert not any(c[:2] == ["docker", "compose"] for c in docker.calls)


def test_destroy_holds_its_lock_through_deletion_so_a_waiting_up_sees_the_state_after_it(tmp_path, monkeypatch):
    """Deterministic: while rmtree runs, an `up` is waiting on the stable lock. It acquires it only after the removal."""
    import threading
    import time

    from scripts.poc_lib import up as poc_up
    from tests.unit.test_poc_up import FakeRunner, make_repo

    repo = make_repo(tmp_path)
    folder = make_stack(repo)
    (folder / "backups").mkdir()
    (folder / "backups" / "pack").write_text("encrypted")
    seen = {}
    deleted = threading.Event()
    real_rmtree = lifecycle.shutil.rmtree
    real_secrets = poc_up.ensure_stack_secrets

    def watching_secrets(root, stack, **kwargs):
        seen["deleted_when_up_got_the_lock"] = deleted.is_set()
        seen["backups_when_up_got_the_lock"] = (folder / "backups").exists()
        return real_secrets(root, stack, **kwargs)

    monkeypatch.setattr(poc_up, "ensure_stack_secrets", watching_secrets)
    results = {}

    def second_up():
        try:
            results["marker"] = poc_up.up(repo, "demo", runner=FakeRunner(), resolver=lambda ref: b"", port_picker=lambda: 18400,
                                          platform="linux/amd64", environ={"PATH": "/usr/bin"})
        except Exception as exc:  # noqa: BLE001 - the thread reports whatever happened
            results["error"] = exc

    waiter = threading.Thread(target=second_up)

    def slow_rmtree(path, *args, **kwargs):
        waiter.start()
        time.sleep(0.5)  # the waiting up has had every chance to run: it must still be blocked on the lock
        seen["blocked_during_delete"] = waiter.is_alive() and "deleted_when_up_got_the_lock" not in seen
        real_rmtree(path, *args, **kwargs)
        deleted.set()

    monkeypatch.setattr(lifecycle.shutil, "rmtree", slow_rmtree)
    lifecycle.destroy(repo, "demo", confirm="demo", runner=VolumeDocker(owned_labels()), environ={"PATH": "/usr/bin"})
    waiter.join(timeout=30)
    assert seen["blocked_during_delete"] is True
    assert seen["deleted_when_up_got_the_lock"] is True and seen["backups_when_up_got_the_lock"] is False
    assert (repo / ".poc" / ".locks" / "demo.lock").exists()  # the lock outlived the folder it protects

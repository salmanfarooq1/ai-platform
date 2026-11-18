"""`poc backup`, `poc down` and `poc status`: the safe lifecycle around a stack's data.

`down` removes a stack's runtime data and compute, so it proves first that nothing would be lost: it stops the API and
worker, then checks in this order: the stack marker (when the context loads), `POC_RECOVERY_REF` is the latest backup, the
live row counts, chain heads, checkpoints, schema head and object list equal the manifest, the backup is not older than
`POC_BACKUP_MAX_AGE_SECONDS` (default 86400) and finally `restic check --read-data` plus a scratch restore pass. A refusal starts the services again and removes nothing. A pending restore (`restore-pending.json`) makes `backup` and
`down` refuse. Every runtime volume removal is checked: a failed removal fails `down`.
The key, the repository password, the repository, the pointer and the marker are never removed; the next `poc up` restores.
"""
import hmac
import json
import os
import shutil
import stat
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from scripts.poc_backup import capture, catalog, pending, pg, verify, volumes
from scripts.poc_backup.catalog import state_of
from scripts.poc_backup.model import BackupRef, DbState, DownProof
from scripts.poc_backup.restore import VALKEY_LOST
from scripts.poc_lib.context import StackContext, lifecycle_lock, load_context
from scripts.poc_lib.keys import StackSecrets
from scripts.poc_lib.runner import CommandError, LocalRunner, Runner
from scripts.poc_lib.up import OWNER_FILE, PocError, StackAbsent, _private_stack_dir, validate_stack

__all__ = ["BackupRef", "DbState", "DownProof", "RealBackend", "StackContext", "backup", "down", "load_context",
           "destroy", "load_manifest", "stack_secrets", "state_of", "status"]

DEFAULT_MAX_AGE_SECONDS = 86400
WAIT_APP = "240"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Backend(Protocol):
    def stop_writers(self) -> None: ...
    def start_writers(self) -> None: ...
    def latest(self) -> BackupRef | None: ...
    def live_state(self) -> DbState: ...
    def verify(self, ref: BackupRef) -> None: ...
    def destroy(self, proof: DownProof) -> None: ...


def stack_secrets(context: StackContext) -> StackSecrets:
    return context.secrets()


def load_manifest(context: StackContext, ref: BackupRef) -> dict[str, Any]:
    manifest, digest = catalog.read_manifest_from_snapshot(context, ref.snapshot_id)
    if digest != ref.manifest_sha256:
        raise PocError("the stored manifest does not match the published digest")
    return manifest


def _reload_after_lock(context: StackContext) -> StackContext:
    """The context was loaded before the lock; whatever held the lock may have changed or removed the stack since."""
    _private_stack_dir(context.stack_dir)
    return load_context(context.root, context.stack, runner=context.runner, environ=context.environ)


def _lock_path(root: Path, stack: str, environ: Mapping[str, str] | None) -> Path:
    stack_dir = Path(os.path.abspath(root)) / ".poc" / stack
    if not stack_dir.parent.exists():
        host = (os.environ if environ is None else environ).get("DOCKER_HOST", "")
        if host and not host.startswith(("unix://", "npipe://")):
            raise PocError("remote Docker engines are not supported: unset DOCKER_HOST")
        raise StackAbsent("no stack marker: no .poc folder exists for this stack")
    return stack_dir


def backup(root: Path, stack: str, *, runner: Runner | None = None, environ: Mapping[str, str] | None = None,
           clock: Callable[[], datetime] = _utcnow) -> BackupRef:
    """Online backup of a running stack. Returns the published reference."""
    validate_stack(stack)
    stack_dir = _lock_path(root, stack, environ)
    with lifecycle_lock(stack_dir):
        context = load_context(root, stack, runner=runner or LocalRunner(), environ=environ)
        context = _reload_after_lock(context)
        pending.refuse_if_pending(context.stack_dir, "backup")  # `latest` must never move to a partially restored state
        return capture.capture(context, clock=clock)


def _max_age(environ: Mapping[str, str]) -> int:
    raw = environ.get("POC_BACKUP_MAX_AGE_SECONDS")
    if raw is None:
        return DEFAULT_MAX_AGE_SECONDS
    if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
        raise PocError("POC_BACKUP_MAX_AGE_SECONDS must be a positive whole number of seconds")
    return int(raw)


def _check_ref(latest: BackupRef | None, wanted: str, stack: str) -> BackupRef:
    if latest is None:
        raise PocError("there is no published backup: run poc backup, then set POC_RECOVERY_REF to the id it prints")
    if latest.stack != stack:
        raise PocError("the latest backup belongs to another stack")
    wanted = wanted.strip().lower()
    if not wanted:
        raise PocError("POC_RECOVERY_REF is not set: set it to the id that poc backup printed (the latest backup)")
    if len(wanted) < 8 or not latest.snapshot_id.startswith(wanted):
        raise PocError("POC_RECOVERY_REF is not the latest backup: run poc backup and use the id it prints")
    return latest


def down(root: Path, stack: str, *, runner: Runner | None = None, environ: Mapping[str, str] | None = None,
         clock: Callable[[], datetime] = _utcnow, backend: Backend | None = None) -> DownProof:
    validate_stack(stack)
    stack_dir = _lock_path(root, stack, environ)
    with lifecycle_lock(stack_dir):
        context = load_context(root, stack, runner=runner or LocalRunner(), environ=environ)
        context = _reload_after_lock(context)  # the marker and the folder may have changed while the lock was held by another
        pending.refuse_if_pending(context.stack_dir, "down")
        backend = backend or RealBackend(context)
        backend.stop_writers()  # no new writes can arrive while the proof is being made
        try:
            latest = _check_ref(backend.latest(), context.environ.get("POC_RECOVERY_REF", ""), stack)  # gate 2
            live = backend.live_state()  # gate 3: nothing changed since the backup (counts, heads, checkpoints, schema, objects)
            if (live.comparable() != latest.state.comparable() or live.schema_head != latest.state.schema_head
                    or sorted(live.objects) != sorted(latest.state.objects)):
                raise PocError("data written after backup; run poc backup")
            age = (clock() - latest.created_at).total_seconds()  # gate 4
            limit = _max_age(context.environ)
            if age < 0 or age > limit:
                raise PocError(f"the latest backup is too old or dated in the future ({int(age)}s; limit {limit}s): run poc backup")
            backend.verify(latest)  # gate 5
            again = backend.latest()  # the proof is for exactly this snapshot and manifest
            if again is None or (again.snapshot_id, again.manifest_sha256) != (latest.snapshot_id, latest.manifest_sha256):
                raise PocError("the latest backup changed during the checks; run poc backup and try again")
        except BaseException:
            try:
                backend.start_writers()
            except Exception:  # noqa: BLE001 - the refusal itself is the message; restarting is best effort
                pass
            raise
        proof = DownProof(stack, latest.snapshot_id, latest.manifest_sha256)
        backend.destroy(proof)
        return proof


class RealBackend:
    """The Docker-backed implementation of the `down` steps."""

    def __init__(self, context: StackContext, *, before_scratch_restore: Callable[[], None] | None = None) -> None:
        self.context = context
        self.before_scratch_restore = before_scratch_restore

    def stop_writers(self) -> None:
        self.context.compose("stop", "api", "worker")

    def start_writers(self) -> None:
        self.context.compose("up", "-d", "--wait", "--wait-timeout", WAIT_APP, "api", "worker")

    def latest(self) -> BackupRef | None:
        return catalog.latest_ref(self.context)

    def live_state(self) -> DbState:
        return pg.state_of(self.context)

    def verify(self, ref: BackupRef) -> None:
        verify.verify_snapshot(self.context, ref, before_scratch_restore=self.before_scratch_restore)

    def destroy(self, proof: DownProof) -> None:
        """Remove this stack's containers and its marker-listed volumes. Keep the key, password, repository, pointer, marker."""
        if proof.stack != self.context.stack:
            raise PocError("the proof is for another stack")
        volumes.present_owned_volumes(self.context)  # refuses a foreign or unsafe volume before anything is removed
        self.context.compose("down", "--remove-orphans")  # no --volumes: volumes go by exact, verified name only
        volumes.remove_owned_volumes(self.context)  # fails on any failed removal and checks each volume is gone


def _force_remove(function: Callable[..., Any], path: str, _info: Any) -> None:
    """rmtree's error handler: a read-only directory a tool left behind is made writable once, then removed."""
    try:
        os.chmod(path, 0o700, follow_symlinks=False)
    except (OSError, NotImplementedError):
        pass
    function(path)


def _check_owner(stack_dir: Path, owner_token: str | None) -> None:
    """With an owner token, only the stack that `up --create-only` stamped with exactly that token may be destroyed."""
    if owner_token is None:
        return
    try:
        fd = os.open(stack_dir / OWNER_FILE, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, encoding="ascii") as stream:
            info = os.fstat(stream.fileno())
            stored = stream.read(128).strip()
        valid = stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
    except (OSError, UnicodeDecodeError):
        raise PocError("this stack carries no owner token: it was not created by this caller; refusing to destroy it") from None
    if not valid or not hmac.compare_digest(stored.encode(), owner_token.encode()):
        raise PocError("the owner token does not match this stack: it was not created by this caller; refusing to destroy it")


def destroy(root: Path, stack: str, *, confirm: str | None, runner: Runner | None = None,
            environ: Mapping[str, str] | None = None, owner_token: str | None = None) -> None:
    """The explicit, total end of a stack: its containers, runtime volumes and images, then the whole `.poc/<stack>` folder
    (receipt key, repository password, backups, marker). The checked `down` keeps all of those so the next `up` restores;
    this does not, so it needs the exact stack name as `confirm` and refuses anything the marker does not own.

    Order: name confirmation, the stack folder is private and not a link, the marker, the lifecycle lock (held until the folder is gone), the owner token when one is given, every volume
    proven ours (by name, label and kind) before anything is removed, containers, volumes, images, and last the folder.
    A refusal or a failed volume removal leaves the key and the backups in place. A pending restore is abandoned on purpose."""
    validate_stack(stack)
    if confirm != stack:
        raise PocError("destroy removes the key and every backup of this stack for good: pass --confirm with the exact stack name")
    stack_dir = Path(os.path.abspath(root)) / ".poc" / stack
    with lifecycle_lock(stack_dir):
        _private_stack_dir(stack_dir)  # revalidate after acquiring the stable lock
        context = load_context(root, stack, runner=runner or LocalRunner(), environ=environ)
        _check_owner(context.stack_dir, owner_token)  # before any removal
        volumes.present_owned_volumes(context, volumes.SCRATCH_VOLUMES)  # refuses a foreign or unsafe volume first
        context.compose("down", "--remove-orphans")  # no --volumes: they go by exact, verified name below
        volumes.remove_owned_volumes(context, volumes.SCRATCH_VOLUMES)
        project = str(context.marker["project"])
        for service in ("api", "worker"):  # the two images this stack built; a failure is not fatal (the cache is not data)
            context.runner.run(["docker", "image", "rm", f"{project}-{service}"], env=context.env, check=False)
        try:
            shutil.rmtree(context.stack_dir, onerror=_force_remove)
        except OSError:
            raise PocError("the runtime data is gone but the stack folder could not be removed: delete .poc/<stack> by hand") from None


def status(root: Path, stack: str, *, runner: Runner | None = None, environ: Mapping[str, str] | None = None,
           clock: Callable[[], datetime] = _utcnow) -> dict[str, Any]:
    """Non-secret recovery facts for the operator. Nothing is changed. Never raises for a stopped stack."""
    validate_stack(stack)
    context = load_context(root, stack, runner=runner or LocalRunner(), environ=environ)
    report: dict[str, Any] = {"stack": stack, "project": context.marker["project"],
                              "api_url": f"http://127.0.0.1:{context.marker['api_port']}"}
    try:
        rows = context.compose("ps", "--all", "--format", "json").text
        parsed = [json.loads(line) for line in rows.splitlines() if line.strip()]
        report["services"] = {r["Service"]: {"state": r.get("State"), "health": r.get("Health")} for r in parsed}
    except (CommandError, ValueError, subprocess.SubprocessError):
        report["services"] = {}
    max_age = None
    try:
        max_age = _max_age(context.environ)
    except PocError as exc:
        report["max_age_error"] = str(exc)
    try:
        latest = catalog.latest_ref(context)
    except (PocError, CommandError) as exc:
        report["latest_backup"] = {"error": str(exc)}
    else:
        if latest is None:
            report["latest_backup"] = None
        else:
            age = int((clock() - latest.created_at).total_seconds())
            report["latest_backup"] = {"snapshot_id": latest.snapshot_id, "manifest_sha256": latest.manifest_sha256,
                                       "created_at": latest.created_at.isoformat(), "age_seconds": age,
                                       "within_max_age": max_age is not None and 0 <= age <= max_age,
                                       "counts": dict(latest.state.counts),
                                       "heads": [list(h) for h in latest.state.heads],
                                       "checkpoints": [list(c) for c in latest.state.checkpoints]}
    report["down_needs"] = ["POC_RECOVERY_REF equal to the latest snapshot id",
                            "no writes since the backup (checked after the API and worker stop)",
                            f"backup age at most {max_age or DEFAULT_MAX_AGE_SECONDS} seconds",
                            "restic check --read-data and a scratch restore"]
    report["lost_on_restore"] = {"valkey": VALKEY_LOST, "note": "cost counters are restored on the same UTC day; "
                                 "sessions require sign-in again; queued work is in Postgres and resumes"}
    try:
        marker = pending.read_pending(context.stack_dir)
        report["restore_pending"] = None if marker is None else {
            "snapshot_id": marker["snapshot_id"], "manifest_sha256": marker["manifest_sha256"]}
    except PocError as exc:
        report["restore_pending"] = {"error": str(exc)}
    last = context.stack_dir / "restore-report.json"
    report["last_restore"] = json.loads(last.read_text()) if last.is_file() else None
    return report

"""Restore the latest published backup into fresh, owned storage while API and worker are stopped.

Called by `poc up` after Postgres and Valkey are healthy on new volumes and before any writer starts. Order: read the
latest snapshot, verify its bytes, identity and release; check that the app image's schema head is the manifest's (never
auto-upgrade); load the dump into the EMPTY target; copy and hash-check the objects; compare the restored counts, chain
heads and checkpoints with the manifest; on the UTC day the restore began, bring the cost counters up to their captured
values with INCRBY (idempotent: a resumed attempt never applies them twice). A failure leaves the repository, the pointer,
the key and the stack marker untouched, the writers stopped and `restore-pending.json` in place (see `pending.py`):
the next `poc up` resumes from the same snapshot.
"""
import hashlib
import io
import json
import tarfile
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.poc_backup import catalog, pending, pg, verify, volumes
from scripts.poc_backup.model import BackupRef, DbState
from scripts.poc_backup.restic import Restic
from scripts.poc_lib.context import StackContext
from scripts.poc_lib.runner import CommandError
from scripts.poc_lib.up import PocError, _write_private

# What an empty Valkey loses (it is not part of the data backup). Everything pending in the job queue, run state, outbox
# and dedupe tables is in Postgres and comes back; the cost counters are re-applied below.
VALKEY_LOST = ["rate_limit_windows", "cache_entries", "sessions", "token_counters", "breaker_state", "leases"]
COUNTER_TTL_SECONDS = 90000  # the same lifetime the gateway gives a daily counter


def counters_to_apply(manifest: dict[str, Any], today: str) -> dict[str, int]:
    """The captured cost counters, only when the restore runs on the same UTC day they belong to."""
    costs = manifest.get("cost_counters") or {}
    if costs.get("date") != today:
        return {}
    return {str(k): int(v) for k, v in dict(costs.get("counters", {})).items() if int(v) > 0}


def load_into_empty_database(context: StackContext, directory: Path, manifest: dict[str, Any]) -> DbState:
    """Load the dump into the app database, which must hold no table yet. Refuses to overwrite anything."""
    tables = context.psql("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'").strip()
    if tables != "0":
        raise PocError("the target database is not empty; refusing to restore over existing data")
    try:
        pg.restore_dump(context, directory / "dump.pgc", pg.DATABASE)
    except CommandError:
        raise PocError("the dump could not be loaded into the target database") from None
    actual = pg.state_of(context)
    verify.compare_state(actual, catalog.state_of(manifest))
    return actual


def _object_tar(directory: Path, manifest: dict[str, Any]) -> Path:
    handle = tempfile.NamedTemporaryFile(dir=directory.parent, prefix="objects-", suffix=".tar", delete=False)
    with tarfile.open(fileobj=handle, mode="w") as archive:
        for entry in manifest["objects"]:
            key = entry["key"]
            data = (directory / "objects" / key).read_bytes()
            info = tarfile.TarInfo(f"{key[:2]}/{key}")
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    handle.close()
    return Path(handle.name)


def copy_objects(context: StackContext, directory: Path, manifest: dict[str, Any]) -> int:
    """Write the objects into the new object volume (the API container is not running: a one-off run) and re-hash them
    where they now live. Returns how many were verified."""
    if not manifest["objects"]:
        return 0
    archive = _object_tar(directory, manifest)
    try:
        context.compose("run", "--rm", "--no-deps", "-T", "api", "tar", "-x", "-f", "-", "-C", "/data/objects",
                        "--no-same-owner", input_file=archive)
    finally:
        archive.unlink(missing_ok=True)
    listing = context.compose("run", "--rm", "--no-deps", "-T", "api", "sh", "-c",
                              "cd /data/objects && sha256sum */*").text
    found = {line.split()[1].split("/")[-1]: line.split()[0] for line in listing.splitlines() if len(line.split()) == 2}
    for entry in manifest["objects"]:
        if found.get(entry["key"]) != entry["key"]:
            raise PocError("a restored object does not hash to its key; the restore is not healthy")
    return len(manifest["objects"])


def _counter_value(text: str) -> int:
    text = text.strip()
    return int(text) if text.isdigit() else 0  # a missing key prints nothing


def apply_counters(context: StackContext, counters: dict[str, int]) -> dict[str, int]:
    """Bring each counter up to its captured value with INCRBY by the missing amount. On a fresh Valkey that is the whole
    value; a resumed attempt that finds it already applied adds nothing, so a counter is never doubled, and spend recorded
    since is never lowered."""
    restored = {}
    for key, value in sorted(counters.items()):
        missing = value - _counter_value(context.valkey("GET", key))
        if missing > 0:
            context.valkey("INCRBY", key, str(missing))
        context.valkey("EXPIRE", key, str(COUNTER_TTL_SECONDS))
        restored[key] = value
    return restored


def begin_restore(context: StackContext) -> BackupRef:
    """Make the restore durable before any runtime volume exists, and return the snapshot to restore.

    No marker: take the latest verified backup and write the marker. A marker: resume from the snapshot it names (never
    `latest`), after checking it is still there; then stop the writers and remove only this stack's partial runtime
    volumes (restic still holds the recovery material)."""
    marker = pending.read_pending(context.stack_dir)
    if marker is None:
        ref = catalog.latest_ref(context)
        if ref is None:
            raise PocError("no published backup to restore from")
        pending.write_pending(context.stack_dir, ref.snapshot_id, ref.manifest_sha256)
        return ref
    ref = catalog.pinned_ref(context, str(marker["snapshot_id"]), str(marker["manifest_sha256"]))
    volumes.present_owned_volumes(context)  # refuse a foreign or unsafe volume before anything is stopped or removed
    context.compose("stop", "api", "worker")
    context.compose("down", "--remove-orphans")  # no --volumes: they go by exact, verified name below
    volumes.remove_owned_volumes(context)
    return ref


def schema_head_of_release(context: StackContext) -> str:
    out = context.compose("run", "--rm", "--no-deps", "-T", "api", "alembic", "heads").text.split()
    if not out:
        raise PocError("could not read the application's schema head")
    return out[0]


def restore_latest(context: StackContext, *, clock: Callable[[], datetime], ref: BackupRef | None = None) -> dict[str, Any]:
    """Restore into the (empty) database and object volume, and return the restore report (not yet written).
    `ref` is the snapshot a pending restore pinned; without it the latest published backup is used."""
    begun = clock().astimezone(timezone.utc)  # one decision per attempt: which UTC day this restore belongs to
    if ref is None:
        ref = catalog.latest_ref(context)
    if ref is None:
        raise PocError("no published backup to restore from")
    restic = Restic(context)
    try:
        directory = restic.restore(ref)
        raw = (directory / "manifest.json").read_bytes()
        manifest = json.loads(raw)
        if hashlib.sha256(raw).hexdigest() != ref.manifest_sha256:
            raise PocError("the restored manifest does not match the published digest")
        verify.verify_restore_set(context, directory, manifest, check_database=False)
        if schema_head_of_release(context) != manifest["schema_head"]:
            raise PocError("the backup's schema version is not this release's schema; refusing to restore or auto-upgrade")
        state = load_into_empty_database(context, directory, manifest)
        objects = copy_objects(context, directory, manifest)
        counters = apply_counters(context, counters_to_apply(manifest, begun.strftime("%Y-%m-%d")))
    finally:
        restic.cleanup_restore()
    return {
        "snapshot_id": ref.snapshot_id, "manifest_sha256": ref.manifest_sha256,
        "verified_at": clock().astimezone(timezone.utc).isoformat(),
        "verified_state": {"counts": dict(state.counts), "heads": [list(h) for h in state.heads],
                           "checkpoints": [list(c) for c in state.checkpoints]},
        "objects_verified": objects, "cost_counters_restored": counters, "valkey_lost": VALKEY_LOST,
        "non_durable_work_lost": [],
    }


def write_report(context: StackContext, report: dict[str, Any]) -> None:
    _write_private(context.stack_dir / "restore-report.json", json.dumps(report, indent=2, sort_keys=True) + "\n", replace=True)

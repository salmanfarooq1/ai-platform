"""Online capture: one lock, one dump, one staging folder, one manifest, one snapshot, then the pointer moves.

Order (pre-start review R1): take the backup lock; `pg_dump -Fc` inside the postgres container to private staging, check
its exit code, hash it; load the dump into a scratch database and read the counts, chain heads and object references from
THAT, never from later live reads; copy and re-hash every referenced object; read today's cost counters; write
`manifest.json`; release the lock; run one tagged `restic backup`; read the manifest back from restic and compare hashes;
only then publish `latest.json`. Any failure stops there: nothing is published and `latest` does not move.
"""
import hashlib
import json
import re
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.poc_backup import catalog, pg
from scripts.poc_backup.model import BackupRef, DbState
from scripts.poc_backup.restic import Restic, private_dir
from scripts.poc_lib.context import StackContext
from scripts.poc_lib.runner import CommandError
from scripts.poc_lib.up import PocError

OBJECT_KEY = re.compile(r"[0-9a-f]{64}")
COST_KEY = re.compile(r"cost:[0-9a-f-]{36}:\d{4}-\d{2}-\d{2}")
OBJECT_ROOT = "/data/objects"


def stage_objects(context: StackContext, state: DbState, staging: Path) -> list[dict[str, Any]]:
    """Copy each referenced content-addressed object out of the object volume and re-hash it. Refuses anything unsafe,
    missing or corrupt. Unreferenced (newer) objects are not copied: the dump does not point to them."""
    objects_dir = private_dir(staging / "objects")
    entries = []
    for key in sorted(state.objects):
        if not isinstance(key, str) or OBJECT_KEY.fullmatch(key) is None:
            raise PocError("backup refused: an object reference is unsafe (not a SHA-256 key)")
        target = objects_dir / key
        result = context.compose("exec", "-T", "api", "cat", f"{OBJECT_ROOT}/{key[:2]}/{key}", check=False, output_file=target)
        if result.returncode != 0:
            raise PocError(f"backup refused: referenced object {key[:12]} is missing from the object store")
        digest = catalog.sha256_file(target)
        if digest != key:
            raise PocError(f"backup refused: referenced object {key[:12]} is corrupt (its content does not hash to its key)")
        entries.append({"key": key, "sha256": digest, "size": target.stat().st_size})
    return entries


def read_cost_counters(context: StackContext, today: str) -> dict[str, int]:
    keys = context.valkey("--scan", "--pattern", f"cost:*:{today}").split()
    counters = {}
    for key in sorted(keys):
        if COST_KEY.fullmatch(key) is None:
            continue
        value = context.valkey("GET", key).strip()
        if value.isdigit():
            counters[key] = int(value)
    return counters


def capture(context: StackContext, *, clock: Callable[[], datetime]) -> BackupRef:
    restic = Restic(context)
    stack_dir = context.stack_dir
    staging = private_dir(stack_dir / "staging", fresh=True)
    private_dir(stack_dir / "restore")
    session = None
    try:
        restic.ensure_repo()
        started = clock().astimezone(timezone.utc)
        today = started.strftime("%Y-%m-%d")
        session = pg.take_backup_lock(context)
        dump = staging / "dump.pgc"
        context.compose("exec", "-T", "postgres", "pg_dump", "-Fc", "-U", "postgres", "-d", pg.DATABASE, output_file=dump)
        dump_hash = catalog.sha256_file(dump)
        with pg.scratch_database(context) as scratch:
            pg.restore_dump(context, dump, scratch)
            state = pg.state_of(context, scratch)
        objects = stage_objects(context, state, staging)
        counters = read_cost_counters(context, today)
        release = stack_dir / "release-manifest.json"
        if not release.is_file():
            raise PocError("backup refused: no release manifest for this stack (run poc up)")
        manifest = {
            "version": 1, "stack": context.stack, "project": context.marker["project"], "database": pg.DATABASE,
            "created_at": started.isoformat(), "schema_head": state.schema_head,
            "dump": {"file": "dump.pgc", "sha256": dump_hash, "size": dump.stat().st_size},
            "objects": objects, "counts": dict(state.counts), "heads": [list(h) for h in state.heads],
            "checkpoints": [list(c) for c in state.checkpoints],
            "signing": context.secrets().public_identity(),  # key id and public key only, never the private key
            "release_manifest_sha256": catalog.sha256_file(release),
            "cost_counters": {"date": today, "counters": counters},
        }
        raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        (staging / "manifest.json").write_bytes(raw)
        (staging / "manifest.json").chmod(0o600)
        manifest_sha = hashlib.sha256(raw).hexdigest()
        session.assert_held(context)  # still the lock holder, per pg_locks, for the whole capture: else nothing is published
        session.close()  # capture is over: purge may continue while restic copies the staged folder
        session = None
        snapshot_id = restic.backup(manifest_sha)
        stored, stored_sha = catalog.read_manifest_from_snapshot(context, snapshot_id)
        rows = [r for r in restic.snapshots() if r["id"] == snapshot_id]
        if stored_sha != manifest_sha or not rows or f"manifest-{manifest_sha}" not in rows[0].get("tags", []):
            raise PocError("backup refused: the stored snapshot does not match the staged manifest")
        ref = catalog.ref_from(manifest, snapshot_id, manifest_sha)
        catalog.write_pointer(stack_dir, ref)  # last: only a verified snapshot becomes `latest`
        return ref
    except CommandError as exc:
        raise PocError(f"backup failed and nothing was published: {exc}") from None
    finally:
        if session is not None:
            session.close()
        shutil.rmtree(staging, ignore_errors=True)

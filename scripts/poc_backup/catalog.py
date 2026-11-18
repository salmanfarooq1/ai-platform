"""The published `latest` pointer and the proof that it still names the newest, intact snapshot."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.poc_backup.model import BackupRef, DbState
from scripts.poc_backup.restic import Restic
from scripts.poc_lib.context import StackContext
from scripts.poc_lib.up import PocError, _write_private

POINTER = "latest.json"
POINTER_FIELDS = {"snapshot_id", "manifest_sha256", "stack", "created_at"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_pointer(stack_dir: Path) -> dict[str, Any] | None:
    path = stack_dir / POINTER
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return None
    try:
        pointer = json.loads(raw)
        if not isinstance(pointer, dict) or not POINTER_FIELDS <= set(pointer):
            raise ValueError
    except ValueError:
        raise PocError("the latest-backup pointer is unreadable; run poc backup") from None
    return dict(pointer)


def write_pointer(stack_dir: Path, ref: BackupRef) -> None:
    """Publish: the very last step of a backup. Atomic, private, never half written."""
    body = {"snapshot_id": ref.snapshot_id, "manifest_sha256": ref.manifest_sha256, "stack": ref.stack,
            "created_at": ref.created_at.isoformat()}
    _write_private(stack_dir / POINTER, json.dumps(body, sort_keys=True) + "\n", replace=True)


def state_of(manifest: dict[str, Any]) -> DbState:
    return DbState.from_mapping({**manifest, "objects": [o["key"] for o in manifest.get("objects", [])]})


def read_manifest_from_snapshot(context: StackContext, snapshot_id: str) -> tuple[dict[str, Any], str]:
    """The manifest as stored in the repository and its SHA-256 (hashed over the stored bytes)."""
    scratch = context.stack_dir / "restore"
    restic = Restic(context)
    restic._prepare()
    target = scratch / f"manifest-{os.getpid()}.json"
    target.unlink(missing_ok=True)
    try:
        raw = restic.dump(snapshot_id, "manifest.json", target)
    finally:
        target.unlink(missing_ok=True)
    try:
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except ValueError:
        raise PocError("the stored manifest is unreadable") from None


def ref_from(manifest: dict[str, Any], snapshot_id: str, manifest_sha: str) -> BackupRef:
    try:
        return BackupRef(stack=str(manifest["stack"]), snapshot_id=snapshot_id, manifest_sha256=manifest_sha,
                         created_at=datetime.fromisoformat(str(manifest["created_at"])), state=state_of(manifest))
    except (KeyError, TypeError, ValueError):
        raise PocError("the stored manifest is incomplete") from None


def latest_ref(context: StackContext) -> BackupRef | None:
    """The published backup, if it is still what the repository says is newest and its manifest still hashes right."""
    pointer = read_pointer(context.stack_dir)
    if pointer is None:
        return None
    if pointer["stack"] != context.stack:
        raise PocError("the latest backup belongs to another stack")
    rows = Restic(context).snapshots()
    if not rows or rows[0]["id"] != pointer["snapshot_id"]:
        raise PocError("the latest backup changed: the repository has a different newest snapshot; run poc backup")
    manifest, digest = read_manifest_from_snapshot(context, pointer["snapshot_id"])
    if digest != pointer["manifest_sha256"] or f"manifest-{digest}" not in rows[0].get("tags", []):
        raise PocError("the latest backup is incomplete or changed: its manifest does not match the published digest")
    return ref_from(manifest, pointer["snapshot_id"], digest)


def pinned_ref(context: StackContext, snapshot_id: str, manifest_sha256: str) -> BackupRef:
    """The snapshot a pending restore names (not `latest`): it must still be in the repository, carry its manifest tag
    and hold a manifest that hashes to the digest the marker recorded."""
    rows = [r for r in Restic(context).snapshots() if r["id"] == snapshot_id]
    if not rows:
        raise PocError("the snapshot named by the pending restore is missing from the repository; the stack's runtime "
                       "data was left as it is (restore it from a copy of the repository, or inspect .poc/<stack>)")
    manifest, digest = read_manifest_from_snapshot(context, snapshot_id)
    if digest != manifest_sha256 or f"manifest-{digest}" not in rows[0].get("tags", []):
        raise PocError("the snapshot named by the pending restore changed: its manifest no longer matches the recorded digest")
    return ref_from(manifest, snapshot_id, digest)

"""The restore-pending marker: a restore is a durable, resumable state, never a half-finished one nobody knows about.

`up` writes `.poc/<stack>/restore-pending.json` (snapshot id and manifest digest) BEFORE the new runtime volumes exist, and
clears it only after the restored data verified, before api and worker start. While it is present `up` never takes the
normal path (migrating an empty or partial database): it resumes the restore from the same snapshot. `backup` and `down`
refuse, so `latest` can never move to a partial state. The file is written atomically (temp file, fsync, rename, mode 0600).
"""
import json
import os
import re
import stat
from pathlib import Path

from scripts.poc_lib.up import PocError, _write_private

PENDING = "restore-pending.json"
_FIELDS = {"snapshot_id", "manifest_sha256", "version"}
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_pending(stack_dir: Path) -> dict[str, object] | None:
    """The marker, or None when no restore is pending. A marker that is unsafe or unreadable refuses: it is never ignored."""
    path = stack_dir / PENDING
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise PocError("the restore-pending marker is unsafe or foreign; refusing to continue (inspect .poc/<stack>)")
    try:
        body = json.loads(path.read_text())
        if (not isinstance(body, dict) or set(body) != _FIELDS or body["version"] != 1
                or not isinstance(body["snapshot_id"], str) or _DIGEST.fullmatch(body["snapshot_id"]) is None
                or not isinstance(body["manifest_sha256"], str) or _DIGEST.fullmatch(body["manifest_sha256"]) is None):
            raise ValueError
    except (ValueError, KeyError, OSError):
        raise PocError("the restore-pending marker is unreadable; refusing to continue (inspect .poc/<stack>)") from None
    return dict(body)


def write_pending(stack_dir: Path, snapshot_id: str, manifest_sha256: str) -> None:
    _write_private(stack_dir / PENDING, json.dumps({"snapshot_id": snapshot_id, "manifest_sha256": manifest_sha256,
                                                    "version": 1}, sort_keys=True) + "\n", replace=True)
    _sync_directory(stack_dir)


def clear_pending(stack_dir: Path) -> None:
    try:
        os.unlink(stack_dir / PENDING)
    except FileNotFoundError:
        return
    _sync_directory(stack_dir)


def refuse_if_pending(stack_dir: Path, action: str) -> None:
    if read_pending(stack_dir) is not None:
        raise PocError(f"a restore is pending for this stack: run `poc up` to finish it before `{action}`")

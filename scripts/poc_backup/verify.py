"""Verify a restored snapshot against its manifest: bytes, identity, release and (optionally) the database it makes.

Used twice with the same checks: `down` runs them on a scratch restore of the latest snapshot before anything is removed,
and `up` runs them on the snapshot it is about to restore, before any writer starts.
"""
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.settings import Settings
from scripts.poc_backup import catalog, pg
from scripts.poc_backup.capture import OBJECT_KEY
from scripts.poc_backup.catalog import state_of
from scripts.poc_backup.keys import validate_restore_key
from scripts.poc_backup.model import BackupRef, DbState
from scripts.poc_backup.restic import Restic
from scripts.poc_lib.context import StackContext
from scripts.poc_lib.up import PocError


def restore_settings(context: StackContext) -> Settings:
    """The recovery identity: the stack's private key file, plus the operator's trusted previous public keys."""
    previous = context.environ.get("RECEIPT_PREVIOUS_PUBLIC_KEYS") or None
    return Settings(_env_file=None, receipt_signing_key_file=str(context.secrets().key_file),  # type: ignore[call-arg]
                    receipt_previous_public_keys=previous)


def verify_bytes(context: StackContext, directory: Path, manifest: dict[str, Any]) -> None:
    """Everything that can be checked without a database: structure, dump hash, every object hash, key and release."""
    try:
        if manifest["version"] != 1 or manifest["stack"] != context.stack:
            raise PocError("manifest is for another stack or version")
        dump = directory / manifest["dump"]["file"]
        if manifest["dump"]["file"] != "dump.pgc" or not dump.is_file() or dump.is_symlink():
            raise PocError("the dump is missing from the snapshot")
        if catalog.sha256_file(dump) != manifest["dump"]["sha256"]:
            raise PocError("the dump does not match the manifest hash (tampered or damaged)")
        for entry in manifest["objects"]:
            key = entry["key"]
            path = directory / "objects" / key
            if OBJECT_KEY.fullmatch(key) is None or not path.is_file() or path.is_symlink():
                raise PocError("an object is missing or unsafe in the snapshot")
            if catalog.sha256_file(path) != key or entry["sha256"] != key or path.stat().st_size != entry["size"]:
                raise PocError("an object does not match its manifest hash (tampered or damaged)")
        release = context.stack_dir / "release-manifest.json"
        if not release.is_file() or catalog.sha256_file(release) != manifest["release_manifest_sha256"]:
            raise PocError("the release manifest differs from the one the backup was taken on")
        identity = manifest["signing"]
    except (KeyError, TypeError, ValueError):
        raise PocError("the manifest is incomplete or malformed") from None
    try:
        validate_restore_key(identity, restore_settings(context))
    except ValueError as exc:
        raise PocError(f"restore key check failed: {exc}") from None


def verify_restore_set(context: StackContext, directory: Path, manifest: dict[str, Any], *,
                       check_database: bool = True) -> DbState:
    """Raise PocError on any mismatch. With `check_database`, load the dump into an owned scratch database and require
    its schema head, every count, chain head, checkpoint and object reference to equal the manifest."""
    verify_bytes(context, directory, manifest)
    expected = state_of(manifest)
    if not check_database:
        return expected
    with pg.scratch_database(context) as scratch:
        try:
            pg.restore_dump(context, directory / "dump.pgc", scratch)
        except Exception:  # noqa: BLE001 - any failure to load the dump means the snapshot is not restorable
            raise PocError("the dump could not be restored into a scratch database") from None
        actual = pg.state_of(context, scratch)
    compare_state(actual, expected)
    return actual


def compare_state(actual: DbState, expected: DbState) -> None:
    if actual.schema_head != expected.schema_head:
        raise PocError("the schema version differs from the manifest")
    if actual.comparable() != expected.comparable():
        raise PocError("row counts, chain heads or checkpoints differ from the manifest")
    if sorted(actual.objects) != sorted(expected.objects):
        raise PocError("the object references differ from the manifest")


def verify_snapshot(context: StackContext, ref: BackupRef, *, before_scratch_restore: Callable[[], None] | None = None) -> None:
    """The `down` gate: restic read-data check, then a real scratch restore with every manifest check."""
    restic = Restic(context)
    restic.check()
    if before_scratch_restore is not None:
        before_scratch_restore()
    try:
        directory = restic.restore(ref)
        raw = (directory / "manifest.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref.manifest_sha256:
            raise PocError("the restored manifest does not match the published digest")
        verify_restore_set(context, directory, json.loads(raw))
    finally:
        restic.cleanup_restore()

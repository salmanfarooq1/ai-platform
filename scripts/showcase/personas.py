"""Idempotent persona setup through public owner-role identity operations.

Pass an existing tenant slug and set MIGRATION_DATABASE_URL privately.
Valid saved keys are reused; other keys are rotated within the manifest tenant.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

from core.identity.admin import (
    AdminError,
    admin_connection,
    create_key,
    create_principal,
    inspect_credential,
    list_keys,
    list_principals,
    revoke_key,
)
from core.identity.models import ALL_SCOPES, PRINCIPAL_KINDS

ROOT = Path(__file__).resolve().parents[2]
PERSONA_IDS = ("producer", "steward", "consumer", "operator", "auditor", "agent-developer")


class SetupError(ValueError):
    """A fixed, secret-free diagnostic that is safe to print."""


class PrivateArgumentParser(argparse.ArgumentParser):
    """Argument values may themselves be credentials; never echo parse errors."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, "FAIL personas: invalid arguments; use --help\n")


def env_name(identifier: str) -> str:
    return "SHOWCASE_KEY_" + identifier.upper().replace("-", "_")


def scopes_sha256(scopes: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(scopes), separators=(",", ":")).encode()).hexdigest()


def load_personas() -> list[dict[str, Any]]:
    result = []
    for identifier in PERSONA_IDS:
        definition = json.loads((ROOT / "data/reference-company/personas" / f"{identifier}.json").read_text())
        scopes = definition["scopes"]
        if (definition["id"] != identifier or definition["kind"] not in PRINCIPAL_KINDS
                or not scopes or not set(scopes) <= ALL_SCOPES or len(scopes) != len(set(scopes))
                or ("admin" in scopes) != (identifier == "operator")):
            raise SetupError("invalid persona definition")
        result.append(definition)
    return result


def check_path(path: Path, *, directory: bool = False) -> bool:
    """lstat before opening; reject redirected, shared or foreign-owned state."""
    # Ancestors may be shared (e.g. /tmp), but may never redirect through a symlink.
    for parent in path.parents:
        if parent.is_symlink():
            raise SetupError("private path has a symlink ancestor")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        raise SetupError("private path is a symlink")
    if info.st_uid != os.getuid():
        raise SetupError("private path has a foreign owner")
    if (directory and not stat.S_ISDIR(info.st_mode)) or (not directory and not stat.S_ISREG(info.st_mode)):
        raise SetupError("private path has the wrong file type")
    if not directory and info.st_nlink != 1:
        raise SetupError("private file has multiple hard links")
    return True


def prepare_directory(path: Path) -> None:
    if not check_path(path, directory=True):
        path.mkdir(mode=0o700)
    path.chmod(0o700)


def validate_state_dir(path: Path) -> Path:
    """Reject unsafe destinations before database or filesystem writes."""
    root = ROOT.resolve()
    if "evidence" in path.parts:
        raise SetupError("private state cannot have an evidence path part")
    check_path(path.absolute(), directory=True)
    resolved = path.resolve()
    if "evidence" in resolved.parts:
        raise SetupError("private state cannot have an evidence path part")
    if resolved == root / ".showcase":
        return resolved
    if not path.is_absolute() or resolved.is_relative_to(root):
        raise SetupError("state directory must be repo .showcase or an absolute path outside the worktree")
    return resolved


def atomic_write(path: Path, content: str) -> None:
    prepare_directory(path.parent)
    check_path(path)
    fd, temporary = tempfile.mkstemp(prefix=".private-", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        check_path(path)
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def private_read(path: Path) -> str:
    if not check_path(path):
        raise SetupError("private setup state is missing")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise SetupError("private state must have the current owner and mode 0600")
        return handle.read()


def read_state(state: Path, slug: str, expected_id: str | None) -> tuple[dict[str, str], dict[str, Any]]:
    keys_path, manifest_path = state / "keys.env", state / "manifest.json"
    manifest: dict[str, Any] = {"tenant_slug": slug, "tenant_id": expected_id, "personas": {}}
    if check_path(manifest_path):
        manifest = json.loads(private_read(manifest_path))
        if (set(manifest) != {"tenant_slug", "tenant_id", "personas"} or manifest["tenant_slug"] != slug
                or (expected_id is not None and manifest["tenant_id"] != expected_id)
                or not set(manifest["personas"]) <= set(PERSONA_IDS)):
            raise SetupError("manifest does not match the requested tenant")
        UUID(manifest["tenant_id"])
    keys: dict[str, str] = {}
    if check_path(keys_path):
        for line in private_read(keys_path).splitlines():
            name, separator, value = line.partition("=")
            if not separator or name in keys or name not in {env_name(p) for p in PERSONA_IDS}:
                raise SetupError("invalid private key file")
            if manifest["personas"]:
                keys[name] = value
    return keys, manifest


def setup(args: argparse.Namespace) -> None:
    state = validate_state_dir(args.state_dir)
    definitions = load_personas()
    dsn = os.environ.get("MIGRATION_DATABASE_URL", "")
    if not dsn:
        raise SetupError("MIGRATION_DATABASE_URL is required")
    for name in ("keys.env", "manifest.json", ".lock"):
        check_path(state / name)
    prepare_directory(state)
    lock_fd = os.open(state / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "w") as lock, admin_connection(dsn) as conn:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        expected_id = str(UUID(args.tenant_id)) if args.tenant_id else None
        keys, manifest = read_state(state, args.tenant, expected_id)
        # Optional fixture verification strengthens the ordinary operator inputs.
        if token := os.environ.get("SHOWCASE_FIXTURE_KEY"):
            caller = inspect_credential(conn, token)
            if (caller["tenant_slug"] != args.tenant
                    or manifest["tenant_id"] not in (None, caller["tenant_id"])):
                raise SetupError("fixture credential does not match the manifest tenant")
            manifest["tenant_id"] = caller["tenant_id"]
        principals = list_principals(conn, args.tenant)
        for definition in definitions:
            identifier, scopes = definition["id"], definition["scopes"]
            entry = manifest["personas"].get(identifier)
            if entry is not None and (set(entry) != {"key_prefix", "scopes_sha256"}
                                      or entry["scopes_sha256"] != scopes_sha256(scopes)):
                raise SetupError("manifest scope metadata does not match persona")
            matches = [p for p in principals if p["name"] == definition["name"]]
            if len(matches) > 1 or (matches and (matches[0]["kind"] != definition["kind"]
                                                or matches[0]["disabled_at"] is not None)):
                raise SetupError("persona principal is ambiguous, disabled or mismatched")
            principal_id = str(matches[0]["id"]) if matches else str(
                create_principal(conn, args.tenant, definition["kind"], definition["name"]))
            token = keys.get(env_name(identifier), "")
            try:
                record = inspect_credential(conn, token)
            except AdminError:
                record = {}
            valid = (entry is not None and record.get("prefix") == entry["key_prefix"]
                     and record.get("tenant_slug") == args.tenant and record.get("principal_id") == principal_id
                     and set(record.get("scopes", [])) == set(scopes))
            if valid and manifest["tenant_id"] not in (None, record["tenant_id"]):
                raise SetupError("saved credential does not match the manifest tenant")
            if not valid or args.replace == identifier:
                previous = list_keys(conn, args.tenant, principal_id=principal_id)
                issued = create_key(conn, principal_id, scopes)
                token = issued.token
                record = inspect_credential(conn, token)
                if manifest["tenant_id"] not in (None, record["tenant_id"]):
                    raise SetupError("operator database does not match the manifest tenant")
                untouched = []
                for key in previous:
                    if key["revoked_at"] is None:
                        if entry is not None and key["prefix"] == entry["key_prefix"]:
                            revoke_key(conn, key["prefix"])
                        else:
                            untouched.append(key["prefix"])
                if untouched:
                    print(f"WARN {identifier}: {len(untouched)} other active key(s) left untouched: {', '.join(untouched)}")
            manifest["tenant_id"] = record["tenant_id"]
            keys[env_name(identifier)] = token
            manifest["personas"][identifier] = {
                "key_prefix": record["prefix"], "scopes_sha256": scopes_sha256(scopes),
            }
        # Metadata first; an interrupted run can safely validate/rotate saved keys again.
        atomic_write(state / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        atomic_write(state / "keys.env", "".join(f"{env_name(p)}={keys[env_name(p)]}\n" for p in PERSONA_IDS))
    print("PASS personas: six credentials verified")


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(prog="setup_personas", description=__doc__)
    parser.add_argument("--tenant", required=True, help="existing tenant slug")
    parser.add_argument("--tenant-id", help="optional expected tenant UUID")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".showcase")
    parser.add_argument("--replace", choices=PERSONA_IDS, help="force rotation of one persona")
    args = parser.parse_args(argv)
    try:
        setup(args)
    except SetupError as exc:
        print(f"FAIL personas: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"FAIL personas: setup stopped ({type(exc).__name__}); inspect private state", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

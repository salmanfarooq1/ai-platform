"""Verify reviewed binary-artifact licence corrections against their installed bytes.

A package version is insufficient: every original wheel member, the lock hash,
the interpreter and platform must match. Original distributed notices are retained.
"""
import hashlib
import importlib.metadata
import json
import marshal
import platform
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("numpy-2.4.2-cp311-linux-x86_64.json")


def verify_members(root: Path, artifact: dict) -> None:
    if any(parent.is_symlink() for parent in (root, *root.parents)):
        raise ValueError("reviewed artifact installation has a symlink parent")
    members = artifact["members"]
    for name, expected in members.items():
        path = root / name
        parents = [root.joinpath(*Path(name).parts[:index]) for index in range(1, len(Path(name).parts))]
        if (not path.is_file() or path.is_symlink() or any(parent.is_symlink() for parent in parents)
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError(f"reviewed artifact member differs: {name}")
    for directory in artifact["directories"]:
        base = root / directory
        if base.is_symlink() or not base.is_dir():
            raise ValueError(f"reviewed artifact directory differs: {directory}")
        for path in base.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"unreviewed artifact symlink: {path.relative_to(root)}")
            if not path.is_file():
                continue
            name = path.relative_to(root).as_posix()
            if name in members or name in artifact["installer_members"]:
                continue
            # Bytecode is generated from the audited sources by the interpreter.
            # It is never a separate licence correction for an extra source member.
            if path.parent.name == "__pycache__" and path.suffix == ".pyc":
                source = path.parent.parent / (path.name.split(".", 1)[0] + ".py")
                if source.relative_to(root).as_posix() in members:
                    try:
                        compiled = marshal.loads(path.read_bytes()[16:])
                        if compiled == compile(source.read_bytes(), str(source), "exec", dont_inherit=True):
                            continue
                    except (EOFError, ValueError, TypeError):
                        pass
            raise ValueError(f"unreviewed installed artifact member: {name}")


def numpy_correction(version: str) -> str:
    artifact = json.loads(MANIFEST.read_text())
    if (version, sys.implementation.cache_tag, sys.platform, platform.machine()) != (
        artifact["version"], artifact["python"], artifact["platform"], artifact["machine"],
    ):
        raise ValueError("NumPy licence correction requires the audited CPython 3.11 Linux x86_64 wheel")
    lock = tomllib.loads((ROOT / "poetry.lock").read_text())
    locked = next(package for package in lock["package"] if package["name"] == "numpy")
    if locked["version"] != version or not any(
        row["file"] == artifact["wheel"] and row["hash"] == "sha256:" + artifact["wheel_sha256"]
        for row in locked["files"]
    ):
        raise ValueError("NumPy lock does not contain the reviewed wheel hash")
    distribution = importlib.metadata.distribution("numpy")
    if distribution.version != version:
        raise ValueError("installed NumPy version differs from reviewed artifact")
    verify_members(Path(distribution.locate_file("")), artifact)
    return artifact["expression"]

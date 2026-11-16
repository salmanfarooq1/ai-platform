"""WP1 private state and persona contracts (test specification 1.4–1.6)."""
import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from core.identity.models import ALL_SCOPES, PRINCIPAL_KINDS
from scripts.showcase import personas

ROOT = Path(__file__).resolve().parents[3]
IDS = {"producer", "steward", "consumer", "operator", "auditor", "agent-developer"}


def test_keys_file_rules(tmp_path, monkeypatch):
    directory = tmp_path / ".showcase"
    personas.prepare_directory(directory)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    target = directory / "keys.env"
    renamed = []
    real_replace = os.replace

    def replace(source, destination, *args, **kwargs):
        source = Path(source)
        assert source.parent == directory
        assert source != target
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        renamed.append(destination)
        return real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(personas.os, "replace", replace)
    personas.atomic_write(target, "private test state\n")
    assert renamed == [target]
    assert target.read_text() == "private test state\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(directory.iterdir()) == [target]
    target.unlink()
    outside = tmp_path / "outside"
    outside.write_text("untouched")
    target.symlink_to(outside)
    with pytest.raises(personas.SetupError, match="symlink"):
        personas.atomic_write(target, "must not write")
    assert outside.read_text() == "untouched"
    target.unlink()
    personas.atomic_write(target, "original")
    # Simulate a different effective user; real filesystem ownership stays unchanged.
    with monkeypatch.context() as patch:
        patch.setattr(personas.os, "getuid", lambda: target.stat().st_uid + 1)
        with pytest.raises(personas.SetupError, match="owner"):
            personas.atomic_write(target, "must not write")
        with pytest.raises(personas.SetupError, match="owner"):
            personas.prepare_directory(directory)
    assert target.read_text() == "original"
    linked = tmp_path / "linked"
    linked.symlink_to(directory, target_is_directory=True)
    with pytest.raises(personas.SetupError, match="symlink"):
        personas.prepare_directory(linked)


def test_ignored_everywhere():
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"], cwd=ROOT,
        input=".showcase/keys.env\n.showcase/manifest.json\n.showcase/m0-server.log\n", text=True, capture_output=True,
    )
    assert result.returncode == 0
    assert set(result.stdout.splitlines()) == {".showcase/keys.env", ".showcase/manifest.json", ".showcase/m0-server.log"}
    for name in (".gitignore", ".dockerignore"):
        rules = (ROOT / name).read_text().splitlines()
        assert ".showcase/" in rules, name
        assert not any(line.startswith("!") and ".showcase" in line for line in rules), name
    assert not (ROOT / ".evidenceignore").exists()
    key_pattern = re.compile(rb"gap_[a-z0-9]{8}_[A-Za-z0-9_-]{32,128}")
    # Exact fixture strings that older unit and e2e tests print (tests/e2e/test_tenancy.py and
    # tests/unit/test_identity_keys.py build them by hand). They were never issued. Nothing else is exempt.
    fixture_keys = {b"gap_abcd1234_" + b"a" * 43, b"gap_abcdefgh_" + b"x" * 43}

    def is_real_key(match: re.Match[bytes]) -> bool:
        return match.group(0) not in fixture_keys

    leaked_paths = [
        str(path.relative_to(ROOT))
        for directory in (ROOT / "planning").rglob("evidence") if directory.is_dir()
        for path in directory.rglob("*")
        if path.is_file() and any(is_real_key(m) for m in key_pattern.finditer(path.read_bytes()))
    ]
    assert not leaked_paths, "platform key pattern found in evidence (contents withheld)"


def test_state_dir_must_be_protected(tmp_path, monkeypatch):
    writes = []

    def attempted_write(path):
        writes.append(path)
        raise personas.SetupError("unexpected write attempt")

    monkeypatch.setenv("MIGRATION_DATABASE_URL", "unused-for-path-validation")
    monkeypatch.setattr(personas, "prepare_directory", attempted_write)
    args = ["--tenant", "fixture", "--tenant-id", "00000000-0000-0000-0000-000000000001"]
    for path in (ROOT / "unprotected", ROOT / "planning/sprints/014-reference-company/evidence/private",
                 tmp_path / "evidence/private", Path("relative-private"), ROOT / ".showcase/evidence"):
        assert personas.main([*args, "--state-dir", str(path)]) != 0
        assert not writes, "unsafe state path reached a write operation"
    assert personas.validate_state_dir(ROOT / ".showcase") == ROOT / ".showcase"
    assert personas.validate_state_dir(Path(".showcase")) == ROOT / ".showcase"
    assert personas.validate_state_dir(tmp_path / "private") == tmp_path / "private"
    redirected = tmp_path / "redirected"
    redirected.symlink_to(tmp_path / "private", target_is_directory=True)
    with pytest.raises(personas.SetupError, match="symlink"):
        personas.validate_state_dir(redirected)


def test_only_existing_scopes():
    paths = sorted((ROOT / "data/reference-company/personas").glob("*.json"))
    assert {path.stem for path in paths} == IDS
    for path in paths:
        persona = json.loads(path.read_text())
        assert set(persona) == {"id", "kind", "name", "scopes", "journey_policies", "notes"}
        assert persona["id"] == path.stem
        assert persona["kind"] in PRINCIPAL_KINDS
        assert persona["scopes"] and set(persona["scopes"]) <= ALL_SCOPES
        assert len(persona["scopes"]) == len(set(persona["scopes"]))
        assert ("admin" in persona["scopes"]) == (path.stem == "operator")
        assert persona["name"] and persona["journey_policies"]
        assert all(isinstance(value, str) and value for value in persona["journey_policies"])
        assert "tenant-wide" in persona["notes"]
        assert "per-persona" in persona["notes"] and "column masking" in persona["notes"]
        if path.stem == "consumer":
            # Query already grants governed KB reads; avoid an unnecessary second scope.
            assert persona["scopes"] == ["query"]


def test_failed_rename_preserves_private_state(tmp_path, monkeypatch):
    directory = tmp_path / ".showcase"
    personas.prepare_directory(directory)
    target = directory / "keys.env"
    personas.atomic_write(target, "original")

    def failed_replace(*args, **kwargs):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(personas.os, "replace", failed_replace)
    with pytest.raises(OSError, match="simulated rename failure"):
        personas.atomic_write(target, "replacement")
    assert target.read_text() == "original"
    assert list(directory.iterdir()) == [target]

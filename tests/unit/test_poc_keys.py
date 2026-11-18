"""WP2: private host files and public-only recovery metadata."""
import base64
import json
import os
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.settings import Settings
from evidence.receipts import keyring_from_settings

ROOT = Path(__file__).resolve().parents[2]


def test_key_created_once_and_survives_down(tmp_path):
    from scripts.poc_lib.keys import ensure_stack_secrets

    def prepare(_):
        files = ensure_stack_secrets(tmp_path, "keytest")
        return files, files.key_file.read_bytes(), files.password_file.read_bytes()

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(prepare, range(12)))
    files = results[0][0]
    before = (files.key_file.read_bytes(), files.password_file.read_bytes())
    assert {(key, password) for _, key, password in results} == {before}
    assert len(base64.b64decode(before[0], validate=True)) == 32
    assert len(before[1]) >= 32
    assert stat.S_IMODE(files.key_file.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(files.key_file.parent.parent.stat().st_mode) == 0o700
    for path in (files.key_file, files.password_file):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert all(s == files for s, _, _ in results)
    repeated_up = ensure_stack_secrets(tmp_path, "keytest")
    assert (repeated_up.key_file.read_bytes(), repeated_up.password_file.read_bytes()) == before
    # Runtime teardown is WP3; the key contract exposes no delete operation.
    runtime = files.key_file.parent / "runtime-fixture"
    runtime.mkdir()
    runtime.rmdir()
    again = ensure_stack_secrets(tmp_path, "keytest", restoring=True)
    assert (again.key_file.read_bytes(), again.password_file.read_bytes()) == before
    with pytest.raises(ValueError, match="missing"):
        ensure_stack_secrets(tmp_path, "missing", restoring=True)
    assert not (tmp_path / ".poc/missing/receipt-signing.key").exists()
    for invalid in ("../escape", "aa", "Upper", "a" * 32):
        with pytest.raises(ValueError):
            ensure_stack_secrets(tmp_path, invalid)


@pytest.mark.parametrize("unsafe", ["root-link", "ancestor-link", "ancestor-dotdot-link", "parent-link", "file-link", "owner", "parent-owner", "mode", "parent-mode", "malformed", "password-mode", "fifo", "hardlink"])
def test_refuses_unsafe_secret_files(tmp_path, monkeypatch, unsafe):
    from scripts.poc_lib.keys import ensure_stack_secrets

    files = ensure_stack_secrets(tmp_path, "keytest")
    if unsafe in {"root-link", "parent-link"}:
        path = files.key_file.parent.parent if unsafe == "root-link" else files.key_file.parent
        destination = path.with_name(path.name + "-real")
        path.rename(destination)
        path.symlink_to(destination, target_is_directory=True)
    elif unsafe in {"ancestor-link", "ancestor-dotdot-link"}:
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError):
            ensure_stack_secrets(alias / ".." if unsafe == "ancestor-dotdot-link" else alias, "keytest")
        return
    elif unsafe == "file-link":
        actual = files.key_file.with_suffix(".real")
        files.key_file.rename(actual)
        files.key_file.symlink_to(actual)
    elif unsafe in {"owner", "parent-owner"}:
        real_fstat = os.fstat
        target = files.key_file if unsafe == "owner" else files.key_file.parent
        inode = target.stat().st_ino

        def foreign(fd):
            info = real_fstat(fd)
            values = list(info)
            if info.st_ino == inode:
                values[4] = os.getuid() + 1
            return os.stat_result(values)

        monkeypatch.setattr(os, "fstat", foreign)
    elif unsafe == "mode":
        files.key_file.chmod(0o644)
    elif unsafe == "parent-mode":
        files.key_file.parent.chmod(0o755)
    elif unsafe == "password-mode":
        files.password_file.chmod(0o644)
    elif unsafe == "fifo":
        files.key_file.unlink()
        os.mkfifo(files.key_file, 0o600)
    elif unsafe == "hardlink":
        os.link(files.key_file, files.key_file.with_suffix(".linked"))
    else:
        files.key_file.write_text("malformed-private-sentinel!")
    with pytest.raises(ValueError) as exc:
        ensure_stack_secrets(tmp_path, "keytest")
    assert "malformed-private-sentinel" not in str(exc.value)


def test_secrets_never_leave_files(tmp_path, monkeypatch, caplog, capsys):
    from scripts.poc_backup.keys import validate_restore_key
    from scripts.poc_lib.keys import ensure_stack_secrets

    # Test repository exclusions with git before blocking all process launches.
    ignored = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT, text=True, capture_output=True,
                             input=".poc/keytest/receipt-signing.key\n.poc/keytest/restic-password\n")
    assert ignored.returncode == 0 and len(ignored.stdout.splitlines()) == 2

    def no_process(*args, **kwargs):
        pytest.fail("secret lifecycle must not launch a subprocess")

    monkeypatch.setattr(subprocess, "run", no_process)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    caplog.set_level("INFO")
    environment = dict(os.environ)
    files = ensure_stack_secrets(tmp_path, "keytest")
    key, password = files.key_file.read_text(), files.password_file.read_text()
    settings = Settings(receipt_signing_key_file=str(files.key_file))
    ring = keyring_from_settings(settings)
    public = files.public_identity()
    assert set(public) == {"key_id", "public_key"}
    assert public["key_id"] == ring.active_key_id
    validate_restore_key(public, settings)
    with pytest.raises(ValueError) as error:
        validate_restore_key({**public, "key_id": "fabricated"}, settings)
    rendered = json.dumps(files.compose_override())
    for service in ("api", "worker"):
        config = files.compose_override()["services"][service]
        assert config["environment"] == {"RECEIPT_SIGNING_KEY_FILE": "/run/secrets/receipt-signing.key"}
        mount = config["volumes"][0]
        assert mount["read_only"] and mount["source"] == str(files.key_file)
        assert mount["bind"]["create_host_path"] is False
    captured = capsys.readouterr()
    exposed = rendered + repr(files) + repr(settings) + settings.model_dump_json() + caplog.text + str(error.value) + json.dumps(public) + captured.out + captured.err
    assert key not in exposed and password not in exposed
    assert dict(os.environ) == environment
    # Docker context has an explicit exclusion as well.
    assert ".poc/" in (ROOT / ".dockerignore").read_text().splitlines()
    assert not list(files.key_file.parent.glob("*.tmp"))

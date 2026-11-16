import logging
from pathlib import Path

import pytest

from core.secrets import SecretRef, SecretRefError, resolve_secret


def test_ref_syntax() -> None:
    assert SecretRef.parse("env:NAME") == SecretRef("env", "NAME")
    assert SecretRef.parse("file:/run/secrets/model") == SecretRef("file", "/run/secrets/model")
    for value in ("NAME", "env:", "file:relative/path", "vault:x", "http://x"):
        with pytest.raises(ValueError):
            SecretRef.parse(value)


def test_file_ref_rules(tmp_path: Path) -> None:
    secure = tmp_path / "secure"
    secure.write_text("value\n", encoding="utf-8")
    secure.chmod(0o600)
    assert resolve_secret(SecretRef("file", str(secure))).reveal() == "value"

    symlink = tmp_path / "link"
    symlink.symlink_to(secure)
    for path, mode in ((symlink, None), (tmp_path / "group-readable", 0o640),
                       (tmp_path / "world-readable", 0o604),
                       (tmp_path / "group-writable", 0o620), (tmp_path, None)):
        if mode is not None:
            path.write_text("value", encoding="utf-8")
            path.chmod(mode)
        with pytest.raises(SecretRefError):
            resolve_secret(SecretRef("file", str(path)))

    empty = tmp_path / "empty"
    empty.write_text("", encoding="utf-8")
    empty.chmod(0o600)
    with pytest.raises(SecretRefError):
        resolve_secret(SecretRef("file", str(empty)))


def test_sentinel_never_leaks(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    sentinel = "sk-SENTINEL-7f3a"
    env_value = sentinel
    monkeypatch.setenv("MODEL_KEY", env_value)
    secret = resolve_secret(SecretRef("env", "MODEL_KEY"))
    caplog.set_level(logging.WARNING)
    logging.getLogger("secret-test").warning("credential=%s", secret)
    rendered = " ".join((repr(secret), str(secret), f"{secret}", caplog.text))
    assert sentinel not in rendered
    assert secret.reveal() == sentinel

    monkeypatch.delenv("MODEL_MISSING", raising=False)
    with pytest.raises(SecretRefError) as missing_error:
        resolve_secret(SecretRef("env", "MODEL_MISSING"))
    assert sentinel not in str(missing_error.value)
    assert env_value not in str(missing_error.value)

    monkeypatch.setenv("MODEL_EMPTY", "\n")
    with pytest.raises(SecretRefError):
        resolve_secret(SecretRef("env", "MODEL_EMPTY"))

    bad_file = tmp_path / "bad-encoding"
    bad_file.write_bytes(sentinel.encode("ascii") + b"\xff")
    bad_file.chmod(0o600)
    with pytest.raises(SecretRefError) as error:
        resolve_secret(SecretRef("file", str(bad_file)))
    assert sentinel not in str(error.value)

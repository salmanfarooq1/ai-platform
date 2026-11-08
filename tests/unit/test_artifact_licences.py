"""An audited version must not grant a correction to different installed artifacts."""
import hashlib
import json
import py_compile
from types import SimpleNamespace

import pytest

from scripts.supply_chain import artifact_licences as audit
from scripts.supply_chain.licence_metadata import permitted

pytestmark = pytest.mark.unit


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    root.mkdir()
    (root / "numpy").mkdir()
    (root / "numpy/a.py").write_text("VALUE = 1\n")
    artifact = {
        "version": "2.4.2", "python": "cpython-311", "platform": "linux", "machine": "x86_64",
        "wheel": "reviewed.whl", "wheel_sha256": "1" * 64, "expression": "MIT",
        "directories": ["numpy"], "installer_members": [],
        "members": {"numpy/a.py": hashlib.sha256((root / "numpy/a.py").read_bytes()).hexdigest()},
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(artifact))
    (tmp_path / "poetry.lock").write_text(
        '[[package]]\nname="numpy"\nversion="2.4.2"\nfiles=[{file="reviewed.whl",hash="sha256:' + "1" * 64 + '"}]\n'
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "MANIFEST", manifest)
    monkeypatch.setattr(audit.sys.implementation, "cache_tag", "cpython-311")
    monkeypatch.setattr(audit.sys, "platform", "linux")
    monkeypatch.setattr(audit.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(audit.importlib.metadata, "distribution", lambda _: SimpleNamespace(
        version="2.4.2", locate_file=lambda _: root,
    ))
    return root, artifact


def test_exact_installed_artifact_can_use_reviewed_expression(artifact):
    assert audit.numpy_correction("2.4.2") == "MIT"


@pytest.mark.parametrize("change", ["version", "platform", "wheel_hash", "missing", "tampered", "extra", "binary", "symlink", "directory_symlink", "parent_symlink", "bytecode"])
def test_artifact_drift_fails_closed(artifact, monkeypatch, change):
    root, _ = artifact
    version = "2.4.2"
    if change == "version":
        version = "2.4.3"
    elif change == "platform":
        monkeypatch.setattr(audit.platform, "machine", lambda: "aarch64")
    elif change == "wheel_hash":
        (audit.ROOT / "poetry.lock").write_text((audit.ROOT / "poetry.lock").read_text().replace("1" * 64, "2" * 64))
    elif change == "missing":
        (root / "numpy/a.py").unlink()
    elif change == "tampered":
        (root / "numpy/a.py").write_text("VALUE = 2\n")
    elif change == "extra":
        (root / "numpy/foreign.py").write_text("# unreviewed code\n")
    elif change == "binary":
        (root / "numpy/foreign.so").write_bytes(b"unreviewed binary")
    elif change == "symlink":
        (root / "numpy/a.py").rename(root / "original.py")
        (root / "numpy/a.py").symlink_to(root / "original.py")
    elif change == "directory_symlink":
        (root / "numpy/extra").symlink_to(root, target_is_directory=True)
    elif change == "parent_symlink":
        (root / "numpy").rename(root / "original")
        (root / "numpy").symlink_to(root / "original", target_is_directory=True)
    elif change == "bytecode":
        py_compile.compile(str(root / "numpy/a.py"), doraise=True)
        next((root / "numpy/__pycache__").iterdir()).write_bytes(b"foreign bytecode")
    with pytest.raises(ValueError):
        audit.numpy_correction(version)


def test_generated_bytecode_must_match_audited_source(artifact):
    root, _ = artifact
    py_compile.compile(str(root / "numpy/a.py"), doraise=True)
    assert audit.numpy_correction("2.4.2") == "MIT"


@pytest.mark.parametrize("expression,expected", [
    ("GPL-3.0-or-later WITH GCC-exception-3.1", True),
    ("GPL-3.0-or-later WITH Classpath-exception-2.0", False),
    ("BUSL-1.1 WITH GCC-exception-3.1", False),
    ("GPL-3.0-or-later", False),
    ("MIT OR (GPL-3.0-or-later WITH GCC-exception-3.1)", True),
    ("MIT AND (GPL-3.0-or-later WITH Classpath-exception-2.0)", False),
])
def test_only_exact_reviewed_with_expression_passes(expression, expected):
    assert permitted(expression, {"MIT", "GPL-3.0-or-later WITH GCC-exception-3.1"}) is expected

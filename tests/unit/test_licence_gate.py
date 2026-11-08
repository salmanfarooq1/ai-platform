"""The real gate and seeded metadata use the same OSI allowlist."""
import subprocess

import pytest

from tests.harness import ROOT

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fixture,expected", [("non_osi", 1), ("mit", 0)])
def test_licence_fixture(fixture, expected):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/supply_chain/licence_gate.sh"), "--fixture", str(ROOT / "tests/fixtures/licence" / fixture)],
        capture_output=True, text=True,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert ("BUSL-1.1" if expected else "licence gate ok") in result.stdout + result.stderr


@pytest.mark.parametrize("expression,expected", [
    ("MIT OR BUSL-1.1", True),
    ("MIT AND BUSL-1.1", False),
    ("Apache-2.0 AND MIT", True),
    ("GPL-3.0-or-later WITH GCC-exception-3.1", True),
    ("UNKNOWN", False),
    ("", False),
])
def test_only_approved_licence_choices_pass(expression, expected):
    from scripts.supply_chain.licence_metadata import permitted

    assert permitted(expression, {"MIT", "Apache-2.0"}) is expected


def test_reviewed_exception_is_bound_to_the_exact_package_version(tmp_path, monkeypatch):
    from scripts.supply_chain import licence_metadata as gate

    monkeypatch.setattr(gate, "CHAIN", tmp_path)
    (tmp_path / "osi-licences.txt").write_text("MIT\n")
    (tmp_path / "licence-exceptions.txt").write_text(
        "npm:fixture|1.0|MIT|https://example.test/LICENSE|Reviewed fixture licence.\n"
    )
    assert gate.validate([{"name": "npm:fixture", "version": "1.0", "license": "MIT*"}]) == []
    with pytest.raises(ValueError, match="not approved"):
        gate.validate([{"name": "npm:fixture", "version": "2.0", "license": "MIT*"}])


@pytest.mark.parametrize("name", ["fixture", "npm:fixture"])
def test_reviewed_exception_cannot_approve_a_non_osi_licence(tmp_path, monkeypatch, name):
    from scripts.supply_chain import licence_metadata as gate

    monkeypatch.setattr(gate, "CHAIN", tmp_path)
    (tmp_path / "osi-licences.txt").write_text("MIT\n")
    (tmp_path / "licence-exceptions.txt").write_text(
        f"{name}|1.0|BUSL-1.1|https://example.test/LICENSE|Fixture with forbidden terms.\n"
    )
    with pytest.raises(ValueError, match="not approved"):
        gate.validate([{"name": name, "version": "1.0", "license": "UNKNOWN"}])


@pytest.mark.parametrize("other_name", ["npm:fixture_name", "npm:fixture.name"])
def test_npm_metadata_exception_never_matches_a_different_package_name(tmp_path, monkeypatch, other_name):
    from scripts.supply_chain import licence_metadata as gate

    monkeypatch.setattr(gate, "CHAIN", tmp_path)
    (tmp_path / "osi-licences.txt").write_text("MIT\n")
    (tmp_path / "licence-exceptions.txt").write_text(
        "npm:fixture-name|1.0|MIT|https://example.test/LICENSE|Reviewed exact fixture artifact.\n"
    )
    with pytest.raises(ValueError, match="not approved"):
        gate.validate([{"name": other_name, "version": "1.0", "license": "BUSL-1.1"}])


def test_repository_osi_allowlist_is_subset_of_official_spdx_osi_fixture():
    allowlist = ROOT / "scripts/supply_chain/osi-licences.txt"
    fixture = ROOT / "tests/fixtures/licence/spdx-osi.txt"
    allowed = {line.strip() for line in allowlist.read_text().splitlines() if line.strip() and not line.startswith("#")}
    official = {line.strip() for line in fixture.read_text().splitlines() if line.strip() and not line.startswith("#")}
    assert allowed <= official


def test_psf_exception_is_bound_to_exact_distribution_and_version(tmp_path, monkeypatch):
    from scripts.supply_chain import licence_metadata as gate

    monkeypatch.setattr(gate, "CHAIN", tmp_path)
    (tmp_path / "osi-licences.txt").write_text("MIT\n")
    (tmp_path / "licence-exceptions.txt").write_text(
        "aiohappyeyeballs|2.6.1|PSF-2.0|https://pypi.org/project/aiohappyeyeballs/2.6.1/|Reviewed exact release.\n"
    )
    assert gate.validate([{"name": "aiohappyeyeballs", "version": "2.6.1", "license": "UNKNOWN"}]) == []
    for name, version in (("aiohappyeyeballs", "2.6.2"), ("another-package", "2.6.1")):
        with pytest.raises(ValueError, match="not approved"):
            gate.validate([{"name": name, "version": version, "license": "UNKNOWN"}])

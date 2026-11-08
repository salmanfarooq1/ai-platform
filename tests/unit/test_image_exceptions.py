"""Profile-scoped Grype exceptions are validated without a container engine."""
from datetime import date

import pytest

from scripts.supply_chain.image_exceptions import render_config
from tests.harness import ROOT

pytestmark = pytest.mark.unit
FIXTURES = ROOT / "tests/fixtures/images"
IMAGE = "apache/kafka:4.3.1@sha256:" + "1" * 64
TODAY = date(2026, 10, 24)


def test_optional_image_exception_is_limited_to_its_cve_and_package():
    config = render_config(FIXTURES / "optional-valid", IMAGE, TODAY)
    assert config == {"ignore": [{"vulnerability": "CVE-2026-12345", "fix-state": "fixed", "package": {"name": "openssl"}}]}


def test_expired_image_exception_fails():
    with pytest.raises(ValueError, match="expired exception"):
        render_config(FIXTURES / "expired", IMAGE, TODAY)


@pytest.mark.parametrize("name", ["default", "observability"])
def test_default_and_observability_images_cannot_have_exceptions(name):
    with pytest.raises(ValueError, match="forbidden for default or observability"):
        render_config(FIXTURES / name, IMAGE, TODAY)


def test_no_exception_keeps_empty_grype_ignore_list():
    assert render_config(FIXTURES / "empty", IMAGE, TODAY) == {"ignore": []}

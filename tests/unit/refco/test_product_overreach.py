"""Operator helpers stay general; each decision resource has one URL."""
import pytest

from api.main import create_app
from core.identity import admin


@pytest.mark.parametrize("name", ["identity_admin_lock", "tenant_inventory", "principal_keys"])
def test_no_showcase_only_identity_helpers(name):
    assert not hasattr(admin, name)


def test_decision_resource_has_one_list_url():
    schema = create_app().openapi()
    assert "/v1/decisions" in schema["paths"]
    assert "/v1/console/decisions" not in schema["paths"]

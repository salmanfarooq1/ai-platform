"""Module edition settings and metadata stay independent of module imports."""
import pytest

from core.modules import EDITIONS, MODULES, edition_for, module_metadata, parse_enabled_modules
from core.settings import Settings, SettingsError

pytestmark = pytest.mark.unit


def test_every_module_has_a_valid_pillar_and_unique_name():
    names = [module.name for module in MODULES]
    assert len(names) == len(set(names))
    assert all(module.pillar in {"platform", "gateway", "data", "agents"} for module in MODULES)
    assert sum(module.always_on for module in MODULES) == 1


@pytest.mark.parametrize("edition", ["Gateway", "Assurance", "Agents", "Data", "Full"])
def test_the_five_editions_resolve_to_the_reviewed_module_sets(edition):
    enabled = parse_enabled_modules(",".join(sorted(EDITIONS[edition])))
    assert edition_for(enabled) == edition
    assert all(info["enabled"] == (info["name"] in enabled) for info in module_metadata(enabled))


def test_all_is_the_default_and_gateway_is_mandatory():
    settings = Settings()
    assert settings.deploy_shape == "single_tenant"
    assert settings.enabled_module_names == parse_enabled_modules("all")
    assert parse_enabled_modules("agents,gateway") == frozenset({"agents", "gateway"})
    with pytest.raises(ValueError, match="must include gateway"):
        parse_enabled_modules("agents")


@pytest.mark.parametrize("value", ["", "nonesuch", "gateway,agents,typo"])
def test_unknown_or_empty_module_lists_fail_at_settings_validation(value):
    with pytest.raises((SettingsError, ValueError)):
        Settings(enabled_modules=value)


@pytest.mark.parametrize("value", ["single_tenant", "multi_tenant"])
def test_supported_deploy_shapes(value):
    assert Settings(deploy_shape=value).deploy_shape == value


def test_unknown_deploy_shape_is_refused():
    with pytest.raises((SettingsError, ValueError)):
        Settings(deploy_shape="shared")

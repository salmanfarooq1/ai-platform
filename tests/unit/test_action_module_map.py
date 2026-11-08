"""The gateway module stage has an owner for every action."""
import pytest

from core.modules import MODULE_NAMES, MODULES, module_metadata, parse_enabled_modules
from gateway.module_stage import ACTION_MODULES
from gateway.types import ActionKind

pytestmark = pytest.mark.unit


def test_every_action_kind_maps_to_module():
    assert set(ACTION_MODULES) == set(ActionKind)
    assert set(ACTION_MODULES.values()) <= MODULE_NAMES


def test_modules_have_pillars():
    assert all(module.pillar in {"platform", "gateway", "data", "agents"} for module in MODULES)


def test_modules_have_descriptions():
    assert all(0 < len(module.description) <= 140 for module in MODULES)
    metadata = {item["name"]: item for item in module_metadata(parse_enabled_modules("gateway"))}
    assert all(metadata[module.name]["description"] == module.description for module in MODULES)

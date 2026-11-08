"""Edition and module metadata without importing any module implementation."""
from dataclasses import dataclass
from typing import Literal, TypedDict

Pillar = Literal["platform", "gateway", "data", "agents"]


class ModuleMetadata(TypedDict):
    name: str
    label: str
    pillar: Pillar
    description: str
    enabled: bool
    nav_group: str | None
    always_on: bool


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    label: str
    pillar: Pillar
    description: str
    always_on: bool
    nav_group: str | None = None
    routers: tuple[str, ...] = ()
    transports: tuple[str, ...] = ()
    job_handlers: tuple[str, ...] = ()


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec("gateway", "Gateway", "gateway", "Control access to data and record each decision.", True, "Governance"),
    ModuleSpec("evidence", "Evidence", "gateway", "View signed records that explain how decisions were made.", False, "Evidence"),
    ModuleSpec("agents", "Agents", "agents", "Ask questions and run governed agents against business data.", False, "Workspace", (
        "api.agent.router:router", "api.routers.sandbox:router",
    ), ("api.mcp.transport",), ("api.agent.jobs:build_agent_job_handlers",)),
    ModuleSpec("data", "Data", "data", "Upload, organize and search business documents.", False, "Data"),
    ModuleSpec("lineage", "Lineage", "data", "Trace where data came from and how it changed.", False, "Data"),
)
MODULE_BY_NAME: dict[str, ModuleSpec] = {module.name: module for module in MODULES}
MODULE_NAMES = frozenset(MODULE_BY_NAME)

EDITIONS: dict[str, frozenset[str]] = {
    "Gateway": frozenset({"gateway"}),
    "Assurance": frozenset({"gateway", "evidence"}),
    "Agents": frozenset({"gateway", "agents"}),
    "Data": frozenset({"gateway", "data", "lineage"}),
    "Full": MODULE_NAMES,
}


def parse_enabled_modules(value: str) -> frozenset[str]:
    """Resolve `all` or a comma-separated set; gateway is always included."""
    normalized = value.strip()
    if normalized == "all":
        return MODULE_NAMES
    names = frozenset(part.strip() for part in normalized.split(",") if part.strip())
    unknown = names - MODULE_NAMES
    if unknown:
        raise ValueError(f"unknown ENABLED_MODULES value(s): {', '.join(sorted(unknown))}")
    if "gateway" not in names:
        raise ValueError("ENABLED_MODULES must include gateway")
    return names


def edition_for(enabled: frozenset[str]) -> str | None:
    return next((name for name, modules in EDITIONS.items() if modules == enabled), None)


def module_metadata(enabled: frozenset[str]) -> tuple[ModuleMetadata, ...]:
    return tuple(
        {
            "name": module.name,
            "label": module.label,
            "pillar": module.pillar,
            "description": module.description,
            "enabled": module.name in enabled,
            "nav_group": module.nav_group,
            "always_on": module.always_on,
        }
        for module in MODULES
    )

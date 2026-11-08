"""Typed module metadata returned to clients."""
from typing import Literal

from pydantic import BaseModel


class ModuleInfo(BaseModel):
    name: str
    label: str
    pillar: Literal["platform", "gateway", "data", "agents"]
    description: str
    enabled: bool
    nav_group: str | None
    always_on: bool


class ModuleList(BaseModel):
    edition: str | None
    deploy_shape: Literal["single_tenant", "multi_tenant"]
    modules: list[ModuleInfo]

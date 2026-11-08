"""Typed data access contract; tenant/resource arguments do not grant authority."""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from ports.evidence import JsonValue, freeze_json


@dataclass(frozen=True)
class DataResult:
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, JsonValue], ...]
    snapshot_id: str | None = None

    def __post_init__(self) -> None:
        frozen_rows = tuple(freeze_json(row) for row in self.rows)
        if any(not isinstance(row, Mapping) for row in frozen_rows):
            raise TypeError("data result rows must be JSON objects")
        object.__setattr__(self, "rows", frozen_rows)


class DataAccess(Protocol):
    async def read(self, *, tenant_id: UUID, resource: str) -> DataResult:
        """Read a data resource after authorization has been established elsewhere."""
        ...

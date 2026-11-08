"""Typed adapters for optional modules that are not enabled in this process."""
from typing import Any
from uuid import UUID

from ports import CloudEvent, DataResult, ModuleDisabled


class DisabledDataAccess:
    """A disabled data port that fails closed through the module stage."""

    async def read(self, *, tenant_id: UUID, resource: str) -> DataResult:
        del tenant_id, resource
        raise ModuleDisabled("data module is disabled")


class DroppingLineageEmitter:
    """No-op lineage adapter; this counter is process observability, not durable evidence."""

    def __init__(self) -> None:
        self.dropped_count = 0

    async def emit(self, event: CloudEvent, *, tx: Any = None) -> None:
        del event, tx
        self.dropped_count += 1

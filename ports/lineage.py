"""Optional lineage emission contract."""
from typing import Any, Protocol

from ports.events import CloudEvent


class LineageEmitter(Protocol):
    async def emit(self, event: CloudEvent, *, tx: Any = None) -> None:
        """Emit lineage associated with a change, optionally using its transaction."""
        ...

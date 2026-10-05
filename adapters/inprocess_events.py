"""The default EventBus: handlers run in the publisher's task, in subscription order (ADR-0008).

`tx` is whatever the publisher passes (the gateway passes the connection that wrote the decision row), so a
handler can write in the same transaction. A handler that raises is logged and skipped: the other handlers
still run and the publisher is not failed by a subscriber. A bus that must fail the publisher (the outbox in
Sprint 007) raises from `publish` instead, and the gateway then denies with `decision_unrecorded`.
"""
import logging
from collections import defaultdict
from typing import Any

from ports.events import WILDCARD, CloudEvent, Handler

logger = logging.getLogger("adapters.events")


class InProcessEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, type: str, handler: Handler) -> None:
        self._handlers[type].append(handler)

    async def publish(self, event: CloudEvent, *, tx: Any = None) -> None:
        if not isinstance(event, CloudEvent):
            raise TypeError("publish() takes a CloudEvent")
        for handler in [*self._handlers.get(event.type, []), *self._handlers.get(WILDCARD, [])]:
            try:
                await handler(event, tx)
            except Exception:
                logger.error("event handler failed: type=%s id=%s", event.type, event.id, exc_info=True)

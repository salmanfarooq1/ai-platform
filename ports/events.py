"""EventBus port. Events are CloudEvents 1.0 (strict rule 9), with a `tenantid` extension."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

SPEC_VERSION = "1.0"
WILDCARD = "*"

DECISION_RECORDED = "platform.gateway.decision.v1"
INGEST_COMPLETED = "platform.ingest.completed.v1"
DECISIONS_PURGED = "platform.gateway.purge.v1"


@dataclass(frozen=True)
class EventInfo:
    """What `docs/contracts/` says about one event type. A unit test checks `data_fields` against the real event."""

    type: str
    source: str
    subject: str
    summary: str
    data_fields: tuple[str, ...]


EVENT_CATALOGUE: tuple[EventInfo, ...] = (
    EventInfo(
        DECISION_RECORDED, "/gateway", "the decision id",
        "The gateway recorded a decision, allow or deny. It is written in the decision's transaction. It holds the verdict and ids, never the input text or its hash.",
        ("decision_id", "outcome", "stage", "reason", "action", "resource", "request_id", "execution_id"),
    ),
    EventInfo(
        INGEST_COMPLETED, "/ingest", "the job id",
        "A worker finished an ingest job. It holds ids, the content hash and counts, never file content.",
        ("job_id", "document_id", "namespace", "content_hash", "status", "total_chunks"),
    ),
    EventInfo(
        DECISIONS_PURGED, "/gateway/retention", "the job id",
        "A worker purged expired decision records of one tenant. It holds counts and the chain checkpoint, no decision content.",
        ("job_id", "purged", "retention_days", "checkpoint_position", "checkpoint_hash"),
    ),
)


@dataclass(frozen=True)
class CloudEvent:
    """A CloudEvents 1.0 envelope. `data` is JSON-serialisable and never carries input text."""

    type: str
    source: str
    subject: str | None
    tenantid: str
    data: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    specversion: str = SPEC_VERSION
    datacontenttype: str = "application/json"

    def __post_init__(self) -> None:
        if self.specversion != SPEC_VERSION:
            raise ValueError(f"unsupported CloudEvents specversion {self.specversion!r}")
        for name in ("id", "source", "type", "tenantid"):
            if not getattr(self, name):
                raise ValueError(f"CloudEvent.{name} is required")

    def to_dict(self) -> dict[str, Any]:
        """The CloudEvents JSON structured-mode form."""
        out: dict[str, Any] = {
            "specversion": self.specversion, "id": self.id, "source": self.source, "type": self.type,
            "time": self.time.isoformat(), "datacontenttype": self.datacontenttype,
            "tenantid": self.tenantid, "data": self.data,
        }
        if self.subject is not None:
            out["subject"] = self.subject
        return out

    @classmethod
    def from_dict(cls, body: dict[str, Any]) -> "CloudEvent":
        """The inverse of `to_dict`: the event an outbox row holds."""
        return cls(
            type=body["type"], source=body["source"], subject=body.get("subject"), tenantid=body["tenantid"],
            data=body.get("data") or {}, id=body["id"], time=datetime.fromisoformat(body["time"]),
            specversion=body.get("specversion", SPEC_VERSION),
            datacontenttype=body.get("datacontenttype", "application/json"),
        )


# A handler gets the event and the caller's transaction context (whatever `publish(..., tx=...)` was given).
Handler = Callable[[CloudEvent, Any], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, event: CloudEvent, *, tx: Any = None) -> None:
        """Deliver the event to subscribers of its type (and of `*`). `tx` is passed through to in-process handlers."""
        ...

    def subscribe(self, type: str, handler: Handler) -> None:
        """Call `handler` for each event published with this type. The type `*` matches every event."""
        ...

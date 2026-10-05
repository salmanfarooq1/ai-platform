"""Sandbox events: clean what a driver reports, and write it to `sandbox_events` in batches (Sprint 009, migration 0010).

`detail` holds no secret and no input text. Only a short list of keys is kept, every value is cut to a fixed length,
anything that looks like a credential is replaced, and the whole object stays under a size cap (the table has a CHECK for
the same limit). The writer uses `tenant_connection`, so row-level security applies.
"""
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from core.database.tenant import DbPool, tenant_connection
from ports.sandbox import SandboxEvent, SandboxEventKind

KEPT_KEYS = ("host", "port", "protocol", "path", "binary", "syscall", "limit", "value", "code", "reason", "source", "message")
VALUE_CHARS = 160
MESSAGE_CHARS = 300
DETAIL_BYTES = 1500  # the table refuses more than 2048
MAX_EVENTS_PER_RUN = 500

_CREDENTIALS = re.compile(
    r"(?:\b(?:gap|grt)_[a-z0-9]{8}_[A-Za-z0-9_-]{8,})|(?:\bBearer\s+\S+)|(?:[?&](?:key|token|secret|password|api_key|apikey|access_token)=[^&\s]*)",
    re.IGNORECASE,
)


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Replace credentials: key and run-token shapes, bearer values, secret-looking query values, and any given secret."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return _CREDENTIALS.sub("[redacted]", text)


# A refused connection keeps three fields and nothing free-form: a log line can echo text the redaction does not know.
NETWORK_DENIED_KEYS = ("host", "port", "reason")


def clean_detail(detail: Mapping[str, Any], secrets: Iterable[str] = (), kind: SandboxEventKind | None = None) -> dict[str, Any]:
    """The keeper of the rules above. Unknown keys and non-scalar values are dropped."""
    secrets = tuple(secrets)
    cleaned: dict[str, Any] = {}
    for key in (NETWORK_DENIED_KEYS if kind is SandboxEventKind.NETWORK_DENIED else KEPT_KEYS):
        value = detail.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            continue
        if isinstance(value, (int, float)):
            cleaned[key] = value
            continue
        limit = MESSAGE_CHARS if key == "message" else VALUE_CHARS
        cleaned[key] = redact(value, secrets)[:limit]
    while len(json.dumps(cleaned)) > DETAIL_BYTES and cleaned:
        cleaned.pop("message", None) if "message" in cleaned else cleaned.popitem()
    return cleaned


@dataclass(frozen=True)
class EventRow:
    kind: SandboxEventKind
    at: datetime
    detail: dict[str, Any]


def to_row(event: SandboxEvent, secrets: Iterable[str] = ()) -> EventRow:
    at = event.at if event.at.tzinfo is not None else event.at.replace(tzinfo=timezone.utc)
    return EventRow(event.kind, at, clean_detail(event.detail, secrets, event.kind))


class SandboxEventWriter:
    """Writes the events of one run. A write that fails is raised: the runtime logs it and carries on, because the events
    are what the sandbox reported (an observation), while the gateway decisions are the control record."""

    def __init__(self, pool: DbPool, tenant_id: UUID, execution_id: UUID) -> None:
        self._pool = pool
        self._tenant = tenant_id
        self._execution = execution_id
        self.written = 0

    async def write(self, rows: Sequence[EventRow]) -> None:
        if not rows:
            return
        async with tenant_connection(self._pool, self._tenant) as conn:
            await conn.executemany(
                "INSERT INTO sandbox_events (tenant_id, execution_id, kind, detail, at) VALUES ($1, $2, $3, $4::jsonb, $5)",
                [(self._tenant, self._execution, r.kind.value, json.dumps(r.detail), r.at) for r in rows],
            )
        self.written += len(rows)

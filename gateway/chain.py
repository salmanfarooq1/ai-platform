"""The decision hash chain: canonical JSON, row hashes and a chain check (ADR-0012).

Every `gateway_decisions` row of a tenant carries `prev_hash`, `row_hash` and `chain_position`. The hash is

    row_hash = sha256(canonical_json(decision record) || prev_hash)

where `prev_hash` is the hex `row_hash` of the row before it. The first row of a tenant points at the genesis
hash, `sha256("genesis:<tenant id>")`. A purge deletes the oldest rows and leaves a checkpoint (`position`,
`row_hash`) so the rows that remain still verify.

The decision record holds the fields below and nothing else. It never holds input text: only the SHA-256 that is
already on the row. `scripts/verify/receipt.py` repeats these few functions on purpose, so an auditor can check a
receipt without this code base; a test keeps the two in step.
"""
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

# The fields that make a decision record, in the order of the `gateway_decisions` columns.
RECORD_FIELDS = (
    "id", "tenant_id", "principal_id", "request_id", "action", "resource", "outcome", "stage", "reason",
    "policy_version", "input_sha256", "execution_id", "created_at",
)


def genesis_hash(tenant_id: UUID | str) -> str:
    return hashlib.sha256(f"genesis:{tenant_id}".encode()).hexdigest()


def format_time(value: datetime | str) -> str:
    """One text form for a timestamp: UTC, microseconds, a trailing Z. Postgres keeps microseconds, so this
    round-trips a stored `created_at` exactly."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def decision_record(
    *, id: UUID | str, tenant_id: UUID | str, principal_id: UUID | str | None, request_id: str, action: str,
    resource: str | None, outcome: str, stage: str, reason: str, policy_version: int | None,
    input_sha256: str | None, execution_id: UUID | str | None, created_at: datetime | str,
) -> dict[str, Any]:
    """The record that is hashed and signed. Ids are lower-case text, the time is `format_time`."""
    return {
        "id": str(id), "tenant_id": str(tenant_id), "principal_id": _text(principal_id), "request_id": request_id,
        "action": action, "resource": resource, "outcome": outcome, "stage": stage, "reason": reason,
        "policy_version": policy_version, "input_sha256": input_sha256, "execution_id": _text(execution_id),
        "created_at": format_time(created_at),
    }


def canonical_json(value: Any) -> str:
    """Sorted keys, no spaces, UTF-8 characters kept: the same value always gives the same text."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_row_hash(record: Mapping[str, Any], prev_hash: str) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8") + prev_hash.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class ChainRow:
    position: int
    prev_hash: str
    row_hash: str
    record: Mapping[str, Any]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def verify_chain(rows: Sequence[ChainRow], anchors: Mapping[int, str]) -> list[Check]:
    """Check rows in position order. `anchors` maps a position to the `row_hash` a checkpoint holds there (position
    0 is the genesis hash). The first row must follow an anchor; each later row must follow the one before it, with
    no gap, and every `row_hash` must be the hash of its own record. Returns one check per property."""
    if not rows:
        return [Check("chain_rows", True, "no rows to check")]
    problems_hash: list[str] = []
    problems_link: list[str] = []
    problems_gap: list[str] = []
    first = rows[0]
    anchor = anchors.get(first.position - 1)
    if anchor is None:
        problems_link.append(f"no checkpoint at position {first.position - 1}")
    elif first.prev_hash != anchor:
        problems_link.append(f"position {first.position} does not follow the checkpoint at {first.position - 1}")
    previous = first
    for row in rows:
        if compute_row_hash(row.record, row.prev_hash) != row.row_hash:
            problems_hash.append(f"position {row.position}: the row hash does not match its record")
        if row is not first:
            if row.position != previous.position + 1:
                problems_gap.append(f"position {previous.position} is followed by {row.position}")
            elif row.prev_hash != previous.row_hash:
                problems_link.append(f"position {row.position} does not follow position {previous.position}")
            previous = row
    return [
        Check("row_hashes", not problems_hash, "; ".join(problems_hash) or f"{len(rows)} row hashes match their records"),
        Check("links", not problems_link, "; ".join(problems_link) or "every row points at the row before it"),
        Check("no_gaps", not problems_gap, "; ".join(problems_gap) or "positions are consecutive"),
    ]

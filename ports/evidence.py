"""Typed, SDK-free contracts for durable decision and receipt evidence."""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias
from uuid import UUID

from ports.events import EventBus

JsonValue: TypeAlias = None | bool | int | float | str | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]


def freeze_json(value: object) -> JsonValue:
    """Take ownership of generic JSON data and recursively make it immutable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        copied: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            copied[key] = freeze_json(item)
        from types import MappingProxyType

        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


@dataclass(frozen=True)
class DecisionEntry:
    """Gateway-independent decision input; the sink owns id, timestamp and chain position."""

    tenant_id: UUID
    principal_id: UUID | None
    request_id: str
    trace_id: str
    action: str
    resource: str | None
    outcome: Literal["allow", "deny"]
    stage: str
    reason: str
    policy_version: int | None
    input_sha256: str | None
    execution_id: UUID | None
    extensions: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        frozen = freeze_json(self.extensions)
        if not isinstance(frozen, Mapping):
            raise TypeError("decision extensions must be a JSON object")
        object.__setattr__(self, "extensions", frozen)


class DecisionSink(Protocol):
    async def write(self, entry: DecisionEntry, events: EventBus | None = None) -> UUID:
        """Persist a decision and its transactional publication, raising if the write fails."""
        ...


@dataclass(frozen=True)
class EvidenceRef:
    """Whether a decision has a receipt link visible to the caller."""

    linked: bool
    decision_id: UUID | None = None
    href: str | None = None


class EvidenceLookup(Protocol):
    async def decision(self, tenant_id: UUID, decision_id: UUID) -> EvidenceRef:
        """Return the same unlinked reference for unknown and foreign decision ids."""
        ...

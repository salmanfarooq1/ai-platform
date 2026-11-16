"""Typed, SDK-free model identity and routing contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol

from ports.evidence import JsonValue


class ModelUse(str, Enum):
    COMPLETION = "completion"
    CHAT = "chat"
    EMBEDDING = "embedding"


@dataclass(frozen=True)
class SecretRef:
    """A reference to a secret, never the secret value itself."""

    kind: Literal["env", "file"]
    name: str

    def __post_init__(self) -> None:
        if self.kind == "env":
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name) is None:
                raise ValueError("invalid environment secret reference")
        elif self.kind == "file":
            if not self.name.startswith("/"):
                raise ValueError("file secret references must use an absolute path")
        else:
            raise ValueError("unsupported secret reference")

    @classmethod
    def parse(cls, value: str) -> "SecretRef":
        if value.startswith("env:"):
            return cls("env", value[4:])
        if value.startswith("file:"):
            return cls("file", value[5:])
        raise ValueError("secret reference must use env:NAME or file:/absolute/path")

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"


@dataclass(frozen=True)
class ModelIdentity:
    alias: str
    provider: str
    source: Literal["local", "hosted"]
    digest: str | None
    provider_model_id: str | None
    processing_scope: str
    region: str
    storage_geography: str | None

    def __post_init__(self) -> None:
        has_digest = self.digest is not None
        has_provider_id = self.provider_model_id is not None
        if self.source == "local":
            if not has_digest or has_provider_id:
                raise ValueError("local model identity requires only a SHA-256 digest")
            if re.fullmatch(r"sha256:[0-9a-f]{64}", self.digest or "") is None:
                raise ValueError("local model digest must be sha256 followed by 64 lowercase hex characters")
        elif self.source == "hosted":
            if not has_provider_id or has_digest:
                raise ValueError("hosted model identity requires only a provider model id")
            if not self.provider_model_id:
                raise ValueError("hosted provider model id cannot be empty")

    def as_extension(self, phase: Literal["admission", "attempt"], *, route: str) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "name": self.alias,
            "provider": self.provider,
            "source": self.source,
            "processing_scope": self.processing_scope,
            "region": self.region,
            "route": route,
            "phase": phase,
        }
        if self.digest is not None:
            result["digest"] = self.digest
        if self.provider_model_id is not None:
            result["provider_model_id"] = self.provider_model_id
        return result


@dataclass(frozen=True, eq=False)
class ModelRoute:
    identity: ModelIdentity
    endpoint: str
    credential: SecretRef | None
    params: Mapping[str, JsonValue]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        params = _freeze_json(self.params)
        object.__setattr__(self, "params", params)
        canonical = {
            "identity": {
                "alias": self.identity.alias,
                "provider": self.identity.provider,
                "source": self.identity.source,
                "digest": self.identity.digest,
                "provider_model_id": self.identity.provider_model_id,
                "processing_scope": self.identity.processing_scope,
                "region": self.identity.region,
                "storage_geography": self.identity.storage_geography,
            },
            "endpoint": self.endpoint,
            "credential": str(self.credential) if self.credential is not None else None,
            "params": _thaw_json(params),
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        object.__setattr__(self, "fingerprint", "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest())

    def __hash__(self) -> int:
        return hash(self.fingerprint)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModelRoute):
            return NotImplemented
        return self.fingerprint == other.fingerprint


@dataclass(frozen=True)
class ResolvedModel:
    identity: ModelIdentity
    route: ModelRoute
    use: ModelUse
    price_ref: str | None
    data_use: Literal["training", "no_training", "unknown"]

    def __post_init__(self) -> None:
        if self.route.identity != self.identity:
            raise ValueError("resolved model identity must match route identity")

    def as_extension(self, phase: Literal["admission", "attempt"]) -> dict[str, JsonValue]:
        return self.identity.as_extension(phase, route=self.route.fingerprint)


@dataclass(frozen=True)
class CatalogHealth:
    healthy: bool
    detail: str | None = None


class ModelCatalog(Protocol):
    async def resolve(self, alias: str, *, use: ModelUse) -> ResolvedModel: ...

    async def probe(self) -> CatalogHealth: ...


def _freeze_json(value: object) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError("model route params must be an object")
    frozen: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("model route parameter keys must be strings")
        frozen[key] = _freeze_value(item)
    from types import MappingProxyType

    return MappingProxyType(frozen)


def _freeze_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("model route params must be finite JSON values")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("model route parameter keys must be strings")
        from types import MappingProxyType

        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    raise ValueError("model route params must be JSON values")


def _thaw_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_thaw_json(item) for item in value)
    return value

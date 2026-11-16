"""Validate owned extension JSON before it can become signed evidence.

The registry is deliberately empty in Sprint 012. New entries are reviewed source
changes with a closed JSON Schema, never schemas supplied by a request.
"""
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

MAX_EXTENSION_BYTES = 4096
EXTENSION_SCHEMAS: Mapping[str, Mapping[str, Any]] = MappingProxyType({
    "model": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "provider": {"type": "string", "minLength": 1},
            "source": {"enum": ["local", "hosted"]},
            "digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "provider_model_id": {"type": "string", "minLength": 1},
            "processing_scope": {"type": "string", "minLength": 1},
            "region": {"type": "string"},
            "route": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "phase": {"enum": ["admission", "attempt"]},
        },
        "required": ["name", "provider", "source", "processing_scope", "region", "route", "phase"],
        "oneOf": [
            {"required": ["digest"], "not": {"required": ["provider_model_id"]}},
            {"required": ["provider_model_id"], "not": {"required": ["digest"]}},
        ],
        "additionalProperties": False,
    },
    "stages": {
        "type": "array",
        "maxItems": 9,
        "items": {
            "type": "object",
            "properties": {
                "stage": {"enum": ["principal", "module", "boundary", "model", "policy", "guardrails", "rate", "budget", "cost"]},
                "status": {"enum": ["passed", "denied", "skipped", "not_reached"]},
                "reason": {"type": ["string", "null"]},
                "duration_us": {"type": "integer", "minimum": 0},
            },
            "required": ["stage", "status", "reason", "duration_us"],
            "additionalProperties": False,
        },
    },
    "guardrails": {
        "type": "object",
        "properties": {
            "input_rule_ids": {
                "type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True, "maxItems": 32,
            },
        },
        "required": ["input_rule_ids"],
        "additionalProperties": False,
    },
})


def _plain(value: object, parents: set[int]) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > MAX_EXTENSION_BYTES:
            raise ValueError("extensions exceed the canonical byte limit")
        return value
    if isinstance(value, float):
        raise ValueError("extension numbers must be integers")
    if isinstance(value, (Mapping, list, tuple)):
        identity = id(value)
        if identity in parents:
            raise ValueError("extensions must not contain cycles")
        if len(value) > MAX_EXTENSION_BYTES:
            raise ValueError("extensions exceed the canonical byte limit")
        parents.add(identity)
        try:
            if isinstance(value, Mapping):
                result: dict[str, Any] = {}
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ValueError("extension object keys must be strings")
                    result[key] = _plain(item, parents)
                return result
            return [_plain(item, parents) for item in value]
        finally:
            parents.remove(identity)
    raise ValueError("extensions contain an unsupported JSON value")


def _contains_reference(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(key in {"$ref", "$dynamicRef", "$recursiveRef"} or _contains_reference(item)
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_reference(item) for item in value)
    return False


def validate_extensions(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a private plain-JSON copy; invalid data raises without echoing it."""
    if not isinstance(value, Mapping):
        raise ValueError("extensions must be a JSON object")
    try:
        result: dict[str, Any] = _plain(value, set())
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode("utf-8")
    except (RecursionError, UnicodeError, OverflowError):
        raise ValueError("extensions are not canonical JSON") from None
    if len(encoded) > MAX_EXTENSION_BYTES:
        raise ValueError("extensions exceed the canonical byte limit")
    from jsonschema.exceptions import ValidationError

    for key, item in result.items():
        if key not in EXTENSION_SCHEMAS:
            raise ValueError("extension key is not registered")
        try:
            _validator(key).validate(item)
        except ValidationError:
            raise ValueError("extension does not match its registered schema") from None
    return result


_COMPILED: dict[str, tuple[Mapping[str, Any], Any]] = {}


def _validator(key: str) -> Any:
    """Check and compile a registered schema once; every later write reuses it. Recompiles if the registry entry
    is replaced (tests do this)."""
    from jsonschema import Draft202012Validator

    schema = EXTENSION_SCHEMAS[key]
    hit = _COMPILED.get(key)
    if hit is not None and hit[0] is schema:
        return hit[1]
    if _contains_reference(schema):
        raise ValueError("extension schemas cannot resolve references")
    Draft202012Validator.check_schema(schema)  # a SchemaError here is a source bug, not bad input
    validator = Draft202012Validator(schema)
    _COMPILED[key] = (schema, validator)
    return validator

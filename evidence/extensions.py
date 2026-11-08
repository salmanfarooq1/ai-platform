"""Validate owned extension JSON before it can become signed evidence.

The registry is deliberately empty in Sprint 012. New entries are reviewed source
changes with a closed JSON Schema, never schemas supplied by a request.
"""
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

MAX_EXTENSION_BYTES = 4096
EXTENSION_SCHEMAS: Mapping[str, Mapping[str, Any]] = MappingProxyType({})


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
    for key, item in result.items():
        schema = EXTENSION_SCHEMAS.get(key)
        if schema is None:
            raise ValueError("extension key is not registered")
        if _contains_reference(schema):
            raise ValueError("extension schemas cannot resolve references")
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError, ValidationError

        try:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(item)
        except (SchemaError, ValidationError):
            raise ValueError("extension does not match its registered schema") from None
    return result

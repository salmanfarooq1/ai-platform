"""Tenant policies: the document schema, the engine seam and the loader.

`PolicyEngine` is the seam for a later OPA engine. `PythonPolicyEngine` checks the boundary's resource
allow-lists and the token cap. A tenant with no active policy gets `DEFAULT_POLICY`: what the principal's
scopes grant, over every KB, tool and model, with the platform limits (ADR-0006).
"""
import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.database.tenant import tenant_connection
from gateway.types import Action, ActionKind

if TYPE_CHECKING:
    from gateway.boundary import ExecutionBoundary

logger = logging.getLogger("gateway.policy")

try:
    import config as _config

    _PLATFORM_QUERY_LENGTH = int(_config.GUARDRAIL_CONFIG.get("max_query_length", 1000))
except Exception:  # config is optional here, same fallback as api/services/guardrails.py
    _PLATFORM_QUERY_LENGTH = 1000

PLATFORM_MAX_TOOL_CALLS = 50
PLATFORM_MAX_TOKENS = 100_000

# One tool-argument schema may not be bigger than this once written as JSON (a policy is read on every request).
MAX_TOOL_SCHEMA_BYTES = 8_192

# The tools a policy can name in `tool_arguments`: the agent's tools and the MCP tools and resources. `set-policy` refuses
# any other name, because a typo would protect nothing.
KNOWN_TOOLS = frozenset({
    "retrieve_chunks", "list_namespaces", "search_documents", "multi_namespace_search", "get_ingestion_status",
    "get_cost_summary", "resource_namespaces", "resource_features", "resource_document",
})
# A schema check may not run longer than this. A timeout is a deny.
SCHEMA_CHECK_SECONDS = 0.25
_SCHEMA_MAP_KEYS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")

ResourceList = list[str] | Literal["*"]


class PolicyError(ValueError):
    """A stored or submitted policy document is not valid."""


class PolicyDocument(BaseModel):
    """What a tenant allows. A list that is left out allows nothing (deny by default)."""

    model_config = ConfigDict(extra="forbid")

    allowed_models: ResourceList = Field(default_factory=list)
    allowed_tools: ResourceList = Field(default_factory=list)
    allowed_kbs: ResourceList = Field(default_factory=list)
    max_tool_calls: int = Field(default=PLATFORM_MAX_TOOL_CALLS, ge=0, le=PLATFORM_MAX_TOOL_CALLS)
    max_tokens_per_request: int = Field(default=PLATFORM_MAX_TOKENS, ge=1, le=PLATFORM_MAX_TOKENS)
    max_query_length: int = Field(default=_PLATFORM_QUERY_LENGTH, ge=1, le=_PLATFORM_QUERY_LENGTH)
    blocked_terms: list[str] = Field(default_factory=list)
    # A tenant's own daily cost cap in USD. It can only lower the platform cap (`DAILY_COST_CAP_USD`), never raise it.
    daily_cost_cap_usd: float | None = Field(default=None, gt=0)
    # A JSON Schema per tool name. A call to a tool that has a schema is denied (`tool_argument_not_allowed`) when its
    # arguments do not fit it. A tool without a schema is not checked. A schema may only refer to itself (`#...`).
    tool_arguments: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("tool_arguments")
    @classmethod
    def _schemas_are_valid(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        for name, schema in value.items():
            if not name.strip():
                raise ValueError("tool names must not be blank")
            if len(json.dumps(schema)) > MAX_TOOL_SCHEMA_BYTES:
                raise ValueError(f"the schema of {name!r} is larger than {MAX_TOOL_SCHEMA_BYTES} bytes")
            if _uses_regex(schema):
                raise ValueError(f"the schema of {name!r} uses pattern, patternProperties or format: use enums, lengths and types")
            if _has_foreign_ref(schema):
                raise ValueError(f"the schema of {name!r} refers outside itself")
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise ValueError(f"the schema of {name!r} is not a valid JSON Schema: {exc.message}") from exc
        return value

    @field_validator("allowed_models", "allowed_tools", "allowed_kbs")
    @classmethod
    def _no_blank_or_mixed_wildcard(cls, value: ResourceList) -> ResourceList:
        if value == "*":
            return value
        if any(not v.strip() for v in value):
            raise ValueError("entries must not be blank")
        if "*" in value:
            raise ValueError("use the string \"*\" on its own, not inside a list")
        return value

    @field_validator("blocked_terms")
    @classmethod
    def _terms_not_blank(cls, value: list[str]) -> list[str]:
        if any(not t.strip() for t in value):
            raise ValueError("blocked terms must not be blank")
        return value


def _uses_regex(node: Any) -> bool:
    """True when a schema uses `pattern`, `patternProperties` or `format` (a regex can backtrack without end)."""
    if isinstance(node, dict):
        for key, child in node.items():
            if key in ("pattern", "patternProperties", "format"):
                return True
            if key in _SCHEMA_MAP_KEYS and isinstance(child, dict):  # the keys here are names, the values are schemas
                if any(_uses_regex(v) for v in child.values()):
                    return True
            elif _uses_regex(child):
                return True
    elif isinstance(node, list):
        return any(_uses_regex(child) for child in node)
    return False


def schema_allows(schema: dict[str, Any], arguments: Any) -> bool:
    return bool(Draft202012Validator(schema).is_valid(arguments))


def _has_foreign_ref(node: Any) -> bool:
    """True when the schema has a `$ref` or `$dynamicRef` that does not start with `#` (it would be fetched from outside)."""
    if isinstance(node, dict):
        for key, child in node.items():
            if key in ("$ref", "$dynamicRef") and not (isinstance(child, str) and child.startswith("#")):
                return True
            if _has_foreign_ref(child):
                return True
    elif isinstance(node, list):
        return any(_has_foreign_ref(child) for child in node)
    return False


DEFAULT_POLICY = PolicyDocument(allowed_models="*", allowed_tools="*", allowed_kbs="*")


def parse_policy(raw: Any) -> PolicyDocument:
    """Validate a policy document (dict, or JSON text as asyncpg returns jsonb). Raises PolicyError."""
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        return PolicyDocument.model_validate(data)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PolicyError(f"invalid policy document: {exc}") from exc


class PolicyVerdict(BaseModel):
    allowed: bool
    reason: str = "allowed"


class PolicyEngine(Protocol):
    """Decides whether `action` fits inside `boundary`. The seam for a later OPA engine."""

    async def evaluate(self, boundary: "ExecutionBoundary", action: Action) -> PolicyVerdict: ...


class PythonPolicyEngine:
    async def evaluate(self, boundary: "ExecutionBoundary", action: Action) -> PolicyVerdict:
        kind, resource = action.kind, action.resource
        if kind in (ActionKind.KB_READ, ActionKind.KB_WRITE) and resource is not None:
            if not boundary.allows_kb(resource):
                return PolicyVerdict(allowed=False, reason="kb_not_allowed")
        elif kind is ActionKind.TOOL_CALL:
            if resource is None or not boundary.allows_tool(resource):
                return PolicyVerdict(allowed=False, reason="tool_not_allowed")
            schema = boundary.tool_arguments.get(resource)
            # A tool with a schema and a call that states no arguments is checked as `{}`: it fails closed.
            if schema is not None:
                arguments = dict(action.arguments) if action.arguments is not None else {}
                try:  # off the event loop, with a time limit: a schema that takes too long is a deny
                    ok = await asyncio.wait_for(asyncio.to_thread(schema_allows, dict(schema), arguments), SCHEMA_CHECK_SECONDS)
                except TimeoutError:
                    logger.error("tool argument check timed out for %s", resource)
                    ok = False
                if not ok:
                    return PolicyVerdict(allowed=False, reason="tool_argument_not_allowed")
        elif kind is ActionKind.MODEL_INVOKE:
            if resource is None or not boundary.allows_model(resource):
                return PolicyVerdict(allowed=False, reason="model_not_allowed")
            if action.estimated_tokens is not None and action.estimated_tokens > boundary.max_tokens:
                return PolicyVerdict(allowed=False, reason="token_limit")
        return PolicyVerdict(allowed=True)


async def load_active_policy(pool: Any, tenant_id: UUID) -> tuple[PolicyDocument | None, int | None]:
    """The tenant's active policy and its version, or (None, None) when it has none.

    Raises PolicyError when the active row cannot be parsed: the caller must then deny (fail closed).
    """
    async with tenant_connection(pool, tenant_id) as conn:
        row = await conn.fetchrow("SELECT version, document FROM policies WHERE tenant_id = $1 AND active", tenant_id)
    if row is None:
        return None, None
    return parse_policy(row["document"]), int(row["version"])

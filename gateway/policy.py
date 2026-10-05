"""Tenant policies: the document schema, the engine seam and the loader.

`PolicyEngine` is the seam for a later OPA engine. `PythonPolicyEngine` checks the boundary's resource
allow-lists and the token cap. A tenant with no active policy gets `DEFAULT_POLICY`: what the principal's
scopes grant, over every KB, tool and model, with the platform limits (ADR-0006).
"""
import json
import logging
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import UUID

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

"""ExecutionBoundary: what one request may do. Immutable, built once from scopes and the tenant policy.

`narrow()` returns a subset and raises `BoundaryWidenError` when asked for more than the parent holds. The
agent and its tools receive the boundary (through the enforcement context), never the raw principal.
`"*"` in a resource set means every resource of that type.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from core.identity.models import Principal, Scope
from gateway.policy import DEFAULT_POLICY, PolicyDocument
from gateway.types import ActionKind

WILDCARD = "*"

# What each scope grants, before any tenant policy narrows the resources.
SCOPE_ACTIONS: dict[str, frozenset[str]] = {
    # tool.call is granted to the read scopes because every MCP tool and resource is a gated tool call.
    Scope.KB_READ.value: frozenset({ActionKind.KB_READ.value, ActionKind.TOOL_CALL.value, ActionKind.ANALYTICS_READ.value}),
    # ingest embeds the file, so writing needs the embedding model too
    Scope.KB_WRITE.value: frozenset({ActionKind.KB_WRITE.value, ActionKind.MODEL_INVOKE.value}),
    Scope.QUERY.value: frozenset({
        ActionKind.KB_READ.value, ActionKind.MODEL_INVOKE.value, ActionKind.TOOL_CALL.value, ActionKind.FEEDBACK_WRITE.value,
    }),
    Scope.AGENT.value: frozenset({
        ActionKind.AGENT_RUN.value, ActionKind.TOOL_CALL.value, ActionKind.MODEL_INVOKE.value, ActionKind.KB_READ.value,
    }),
    # The governance console reads decisions, policies, principals and usage. No resource-level narrowing applies.
    Scope.AUDIT_READ.value: frozenset({ActionKind.AUDIT_READ.value}),
    Scope.ADMIN.value: frozenset(k.value for k in ActionKind),
}


class BoundaryWidenError(ValueError):
    """`narrow()` was asked for something the parent boundary does not allow."""


def _within(child: frozenset[str], parent: frozenset[str]) -> bool:
    if WILDCARD in parent:
        return True
    return WILDCARD not in child and child <= parent


@dataclass(frozen=True)
class ExecutionBoundary:
    tenant_id: UUID | None
    actions: frozenset[str]
    kbs: frozenset[str]
    tools: frozenset[str]
    models: frozenset[str]
    max_tool_calls: int
    max_tokens: int
    max_query_length: int
    blocked_terms: frozenset[str]
    policy_version: int | None = None
    # The tenant's own daily cost cap, or None for the platform default (`config.DEFAULT_DAILY_COST_CAP_USD`).
    daily_cost_cap_usd: float | None = None
    # Set when the tenant policy could not be loaded or parsed: every action is then denied.
    unavailable_reason: str | None = None
    # A JSON Schema per tool name (the policy's `tool_arguments`). Narrowing never changes it.
    tool_arguments: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """A JSON form of the boundary, so a job can carry it to a worker (it holds no secret)."""
        return {
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "actions": sorted(self.actions), "kbs": sorted(self.kbs), "tools": sorted(self.tools),
            "models": sorted(self.models), "max_tool_calls": self.max_tool_calls, "max_tokens": self.max_tokens,
            "max_query_length": self.max_query_length, "blocked_terms": sorted(self.blocked_terms),
            "policy_version": self.policy_version, "unavailable_reason": self.unavailable_reason,
            "daily_cost_cap_usd": self.daily_cost_cap_usd, "tool_arguments": dict(self.tool_arguments),
        }

    @classmethod
    def from_payload(cls, body: dict[str, Any]) -> "ExecutionBoundary":
        """The inverse of `to_payload`. The worker runs under the boundary the request had, not a newer policy."""
        return cls(
            tenant_id=UUID(body["tenant_id"]) if body["tenant_id"] else None,
            actions=frozenset(body["actions"]), kbs=frozenset(body["kbs"]), tools=frozenset(body["tools"]),
            models=frozenset(body["models"]), max_tool_calls=int(body["max_tool_calls"]),
            max_tokens=int(body["max_tokens"]), max_query_length=int(body["max_query_length"]),
            blocked_terms=frozenset(body["blocked_terms"]), policy_version=body["policy_version"],
            unavailable_reason=body["unavailable_reason"], daily_cost_cap_usd=body.get("daily_cost_cap_usd"),
            tool_arguments=dict(body.get("tool_arguments") or {}),
        )

    def visible_kbs(self) -> list[str] | None:
        """The KB slugs this boundary allows, sorted, or None when it allows every KB."""
        return None if WILDCARD in self.kbs else sorted(self.kbs)

    def allows_kb(self, slug: str) -> bool:
        return WILDCARD in self.kbs or slug in self.kbs

    def allows_tool(self, name: str) -> bool:
        return WILDCARD in self.tools or name in self.tools

    def allows_model(self, model: str) -> bool:
        return WILDCARD in self.models or model in self.models

    def narrow(
        self,
        *,
        actions: frozenset[str] | set[str] | None = None,
        kbs: frozenset[str] | set[str] | None = None,
        tools: frozenset[str] | set[str] | None = None,
        models: frozenset[str] | set[str] | None = None,
        max_tool_calls: int | None = None,
        max_tokens: int | None = None,
    ) -> "ExecutionBoundary":
        changes: dict[str, Any] = {}
        for name, wanted in (("actions", actions), ("kbs", kbs), ("tools", tools), ("models", models)):
            if wanted is None:
                continue
            child = frozenset(wanted)
            if not _within(child, getattr(self, name)):
                raise BoundaryWidenError(f"{name} would widen the boundary")
            changes[name] = child
        for name, limit in (("max_tool_calls", max_tool_calls), ("max_tokens", max_tokens)):
            if limit is None:
                continue
            if limit < 0 or limit > getattr(self, name):
                raise BoundaryWidenError(f"{name}={limit} would widen the boundary")
            changes[name] = limit
        return replace(self, **changes)


def _resource_set(value: list[str] | str) -> frozenset[str]:
    return frozenset({WILDCARD}) if value == WILDCARD else frozenset(value)


def build_boundary(
    principal: Principal,
    policy: PolicyDocument | None,
    policy_version: int | None = None,
) -> ExecutionBoundary:
    """Scopes decide the action kinds, the tenant policy (or the platform default) the resources and limits."""
    doc = policy if policy is not None else DEFAULT_POLICY
    actions: set[str] = set()
    for scope in principal.scopes:
        actions |= SCOPE_ACTIONS.get(scope, frozenset())
    return ExecutionBoundary(
        tenant_id=principal.tenant_id,
        actions=frozenset(actions),
        kbs=_resource_set(doc.allowed_kbs),
        tools=_resource_set(doc.allowed_tools),
        models=_resource_set(doc.allowed_models),
        max_tool_calls=doc.max_tool_calls,
        max_tokens=doc.max_tokens_per_request,
        max_query_length=min(doc.max_query_length, DEFAULT_POLICY.max_query_length),
        blocked_terms=frozenset(t.casefold() for t in doc.blocked_terms),
        policy_version=policy_version,
        daily_cost_cap_usd=doc.daily_cost_cap_usd,
        tool_arguments=dict(doc.tool_arguments),
    )


def deny_all_boundary(tenant_id: UUID | None, reason: str) -> ExecutionBoundary:
    return ExecutionBoundary(
        tenant_id=tenant_id, actions=frozenset(), kbs=frozenset(), tools=frozenset(), models=frozenset(),
        max_tool_calls=0, max_tokens=0, max_query_length=0, blocked_terms=frozenset(), unavailable_reason=reason,
    )

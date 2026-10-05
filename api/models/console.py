"""Response models of the governance console endpoints (all read-only, tenant-scoped, `audit:read`)."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Outcome = Literal["allow", "deny"]


class PrincipalRef(BaseModel):
    id: UUID
    name: str | None = None


class TenantRef(BaseModel):
    id: UUID
    slug: str


class DecisionSummary(BaseModel):
    id: UUID
    created_at: datetime
    request_id: str
    # None for a decision recorded with no principal.
    principal: PrincipalRef | None
    action: str
    resource: str | None
    outcome: Outcome
    stage: str
    reason: str
    policy_version: int | None


class DecisionDetail(DecisionSummary):
    tenant: TenantRef
    input_sha256: str | None
    # Every decision with the same request_id, oldest first, at most 200.
    trace: list[DecisionSummary]


class DecisionPage(BaseModel):
    items: list[DecisionSummary]
    next_cursor: str | None


class PolicyDocumentView(BaseModel):
    allowed_kbs: list[str] | Literal["*"]
    allowed_tools: list[str] | Literal["*"]
    allowed_models: list[str] | Literal["*"]
    max_tool_calls: int
    max_tokens_per_request: int


class PolicyVersion(BaseModel):
    version: int
    active: bool
    created_at: datetime
    created_by: str | None
    document: PolicyDocumentView


class PolicyList(BaseModel):
    versions: list[PolicyVersion]
    # True when the tenant has no active version, so the platform default applies.
    default_in_effect: bool


class KeySummary(BaseModel):
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class PrincipalSummary(BaseModel):
    id: UUID
    name: str
    kind: str
    created_at: datetime
    keys: list[KeySummary]


class UsageTotals(BaseModel):
    requests: int
    tokens: int
    cost_usd: float


class UsageByPrincipal(BaseModel):
    principal: PrincipalRef
    requests: int
    tokens: int
    cost_usd: float


class UsageByDay(BaseModel):
    date: date
    requests: int
    tokens: int
    cost_usd: float


class DeniedCounts(BaseModel):
    rate: int
    budget: int
    policy: int


class UsageSummary(BaseModel):
    days: int
    totals: UsageTotals
    by_principal: list[UsageByPrincipal]
    by_day: list[UsageByDay]
    denied: DeniedCounts

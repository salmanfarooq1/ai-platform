"""Governance console reads: decisions, policies, principals and usage.

Every route is GET, needs the `audit:read` scope (`admin` holds it), calls `require(audit.read)` so the read
itself leaves a decision row, and queries through `tenant_connection` so row-level security applies. Nothing
here returns a key hash, a secret or any part of a key after its prefix.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import config
from api.auth import require_scope
from api.gateway_deps import gateway_context
from api.models.console import (
    DecisionDetail,
    DecisionPage,
    DecisionSummary,
    DeniedCounts,
    DenyReasonCount,
    FirstDeny,
    KeySummary,
    Overview,
    OverviewBudget,
    OverviewDay,
    PolicyDocumentView,
    PolicyList,
    PolicyVersion,
    PrincipalRef,
    PrincipalSummary,
    ReasonCode,
    RequestDetail,
    RequestPage,
    RequestSummary,
    TenantRef,
    UsageByDay,
    UsageByPrincipal,
    UsageSummary,
    UsageTotals,
)
from api.services.cursor import InvalidCursor, decode_cursor, decode_key_cursor, encode_cursor, encode_key_cursor
from api.services.run_status import with_run_status
from core.database.tenant import DbPool, DbRecord, tenant_connection
from core.identity.models import Principal, Scope
from gateway import Action, ActionKind, DependencyUnavailable, EnforcementContext, require
from gateway.limits import read_budget_used
from gateway.policy import parse_policy
from gateway.reasons import all_reasons

router = APIRouter(tags=["console"])

TRACE_CAP = 200

_DECISION_COLUMNS = """
    d.id, d.created_at, d.request_id, d.principal_id, p.name AS principal_name,
    d.action, d.resource, d.outcome, d.stage, d.reason, d.policy_version, d.execution_id,
    d.record_version, d.extensions
"""
_DECISION_FROM = "FROM gateway_decisions d LEFT JOIN principals p ON p.id = d.principal_id"


async def get_db_pool(request: Request) -> DbPool:
    return request.app.state.db_pool


async def _read(ctx: EnforcementContext, resource: str) -> None:
    """The gateway gate for every console read: `audit.read` on one resource, which writes a decision row."""
    await require(ctx, Action(ActionKind.AUDIT_READ, resource=resource))


def _summary(row: DbRecord) -> DecisionSummary:
    principal = None
    if row["principal_id"] is not None:
        principal = PrincipalRef(id=row["principal_id"], name=row["principal_name"])
    return DecisionSummary(
        id=row["id"], created_at=row["created_at"], request_id=row["request_id"], principal=principal,
        action=row["action"], resource=row["resource"], outcome=row["outcome"], stage=row["stage"],
        reason=row["reason"], policy_version=row["policy_version"], execution_id=row["execution_id"],
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found")


@router.get("/decisions", response_model=DecisionPage)
async def list_decisions(
    request: Request,
    outcome: Literal["allow", "deny"] | None = None,
    action: str | None = None,
    by_principal: UUID | None = Query(default=None, alias="principal", description="Only decisions of this principal id"),
    policy_version: int | None = None,
    request_id: str | None = None,
    execution_id: UUID | None = Query(default=None, description="Only decisions caused by this agent run"),
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> DecisionPage:
    """Decisions of the caller's tenant, newest first, with filters and a keyset cursor."""
    await _read(ctx, "decisions")
    conditions: list[str] = []
    args: list[Any] = []

    def add(sql: str, value: Any) -> None:
        args.append(value)
        conditions.append(sql.format(n=len(args)))

    if outcome is not None:
        add("d.outcome = ${n}", outcome)
    if action is not None:
        add("d.action = ${n}", action)
    if by_principal is not None:
        add("d.principal_id = ${n}", by_principal)
    if policy_version is not None:
        add("d.policy_version = ${n}", policy_version)
    if request_id is not None:
        add("d.request_id = ${n}", request_id)
    if execution_id is not None:
        add("d.execution_id = ${n}", execution_id)
    if since is not None:
        add("d.created_at >= ${n}", since)
    if until is not None:
        add("d.created_at <= ${n}", until)
    if cursor is not None:
        try:
            stamp, row_id = decode_cursor(cursor)
        except InvalidCursor:
            raise HTTPException(status_code=400, detail={"error": "invalid_cursor", "reason": "The cursor is not valid"}) from None
        args.extend([stamp, row_id])
        conditions.append(f"(d.created_at, d.id) < (${len(args) - 1}, ${len(args)})")
    args.append(limit + 1)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = (
        f"SELECT {_DECISION_COLUMNS} {_DECISION_FROM} {where} "
        f"ORDER BY d.created_at DESC, d.id DESC LIMIT ${len(args)}"
    )
    async with tenant_connection(pool, principal.tenant_id) as conn:
        rows = await conn.fetch(sql, *args)
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1]["created_at"], page[-1]["id"]) if len(rows) > limit else None
    items = await with_run_status(pool, principal.tenant_id, [_summary(r) for r in page])
    return DecisionPage(items=items, next_cursor=next_cursor)


async def fetch_decision_detail(pool: DbPool, owner_id: UUID, wanted: UUID) -> DecisionDetail | None:
    """One decision of the tenant with its request trace, or None when it is not the tenant's (or not there)."""
    async with tenant_connection(pool, owner_id) as conn:
        row = await conn.fetchrow(
            f"SELECT {_DECISION_COLUMNS}, d.input_hash {_DECISION_FROM} WHERE d.id = $1", wanted,
        )
        if row is None:
            return None
        trace_rows = await conn.fetch(
            f"SELECT {_DECISION_COLUMNS} {_DECISION_FROM} WHERE d.request_id = $1 "
            f"ORDER BY d.created_at ASC, d.id ASC LIMIT {TRACE_CAP}",
            row["request_id"],
        )
        tenant = await conn.fetchrow("SELECT id, slug FROM tenants WHERE id = $1", owner_id)
    if tenant is None:
        return None
    [base] = await with_run_status(pool, owner_id, [_summary(row)])
    trace = await with_run_status(pool, owner_id, [_summary(r) for r in trace_rows])
    return DecisionDetail(
        **base.model_dump(), tenant=TenantRef(id=tenant["id"], slug=tenant["slug"]),
        input_sha256=row["input_hash"], trace=trace, record_version=row["record_version"],
        extensions=json.loads(row["extensions"]) if isinstance(row["extensions"], str) else row["extensions"],
    )


@router.get("/decisions/{decision_id}", response_model=DecisionDetail)
async def get_decision(
    request: Request,
    decision_id: str,
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> DecisionDetail:
    """One decision with its request trace. A foreign id and a missing id give the same 404."""
    await _read(ctx, "decisions")
    try:
        wanted = UUID(decision_id)
    except ValueError:
        raise _not_found("Decision") from None
    detail = await fetch_decision_detail(pool, principal.tenant_id, wanted)
    if detail is None:
        raise _not_found("Decision")
    return detail


def _policy_version(row: DbRecord) -> PolicyVersion:
    doc = parse_policy(row["document"])
    return PolicyVersion(
        version=row["version"], active=row["active"], created_at=row["created_at"], created_by=row["created_by"],
        document=PolicyDocumentView(
            allowed_kbs=doc.allowed_kbs, allowed_tools=doc.allowed_tools, allowed_models=doc.allowed_models,
            max_tool_calls=doc.max_tool_calls, max_tokens_per_request=doc.max_tokens_per_request,
        ),
    )


@router.get("/policies", response_model=PolicyList)
async def list_policies(
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> PolicyList:
    """Every policy version of the tenant, newest first. `default_in_effect` is true when none is active."""
    await _read(ctx, "policies")
    async with tenant_connection(pool, principal.tenant_id) as conn:
        rows = await conn.fetch("SELECT version, document, created_at, created_by, active FROM policies ORDER BY version DESC")
    versions = [_policy_version(r) for r in rows]
    return PolicyList(versions=versions, default_in_effect=not any(v.active for v in versions))


@router.get("/policies/{version}", response_model=PolicyVersion)
async def get_policy(
    version: int,
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> PolicyVersion:
    await _read(ctx, "policies")
    async with tenant_connection(pool, principal.tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT version, document, created_at, created_by, active FROM policies WHERE version = $1", version,
        )
    if row is None:
        raise _not_found("Policy version")
    return _policy_version(row)


@router.get("/principals", response_model=list[PrincipalSummary])
async def list_principals(
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> list[PrincipalSummary]:
    """Principals and their keys: prefix, scopes and dates only. Never a hash, a secret or the rest of a key."""
    await _read(ctx, "principals")
    async with tenant_connection(pool, principal.tenant_id) as conn:
        people = await conn.fetch("SELECT id, name, kind, created_at FROM principals ORDER BY created_at, id")
        keys = await conn.fetch(
            "SELECT principal_id, prefix, scopes, created_at, last_used_at, revoked_at FROM api_keys ORDER BY created_at, id"
        )
    by_principal: dict[UUID, list[KeySummary]] = {}
    for k in keys:
        by_principal.setdefault(k["principal_id"], []).append(KeySummary(
            prefix=k["prefix"], scopes=sorted(k["scopes"]), created_at=k["created_at"],
            last_used_at=k["last_used_at"], revoked=k["revoked_at"] is not None,
        ))
    return [
        PrincipalSummary(id=p["id"], name=p["name"], kind=p["kind"], created_at=p["created_at"], keys=by_principal.get(p["id"], []))
        for p in people
    ]


@router.get("/usage/summary", response_model=UsageSummary)
async def usage_summary(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to look back"),
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> UsageSummary:
    """Requests, tokens and cost from `usage_log`, by principal and by day, plus the gateway denials by kind.

    `usage_log` has no principal column, so each row is attributed through the `gateway_decisions` rows that
    share its request id. A request with no such row has no principal and is left out of `by_principal`.
    """
    await _read(ctx, "usage")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with tenant_connection(pool, principal.tenant_id) as conn:
        totals = await conn.fetchrow(
            "SELECT COUNT(*) AS requests, COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS tokens, "
            "COALESCE(SUM(cost_usd), 0) AS cost FROM usage_log WHERE created_at >= $1", since,
        )
        by_day = await conn.fetch(
            "SELECT created_at::date AS day, COUNT(*) AS requests, SUM(prompt_tokens + completion_tokens) AS tokens, "
            "SUM(cost_usd) AS cost FROM usage_log WHERE created_at >= $1 GROUP BY 1 ORDER BY 1", since,
        )
        by_principal = await conn.fetch(
            "SELECT p.id, p.name, COUNT(*) AS requests, SUM(u.prompt_tokens + u.completion_tokens) AS tokens, "
            "SUM(u.cost_usd) AS cost FROM usage_log u "
            "JOIN (SELECT DISTINCT request_id, principal_id FROM gateway_decisions WHERE principal_id IS NOT NULL) d "
            "  ON d.request_id = u.request_id "
            "JOIN principals p ON p.id = d.principal_id "
            "WHERE u.created_at >= $1 GROUP BY p.id, p.name ORDER BY cost DESC, p.name", since,
        )
        denied = await conn.fetchrow(
            "SELECT "
            "COUNT(*) FILTER (WHERE reason = 'rate_limit_exceeded') AS rate, "
            "COUNT(*) FILTER (WHERE reason = 'daily_token_budget_exceeded') AS budget, "
            "COUNT(*) FILTER (WHERE stage IN ('policy', 'boundary')) AS policy "
            "FROM gateway_decisions WHERE outcome = 'deny' AND created_at >= $1", since,
        )
    assert totals is not None and denied is not None  # aggregates always return a row
    return UsageSummary(
        days=days,
        totals=UsageTotals(requests=totals["requests"], tokens=int(totals["tokens"]), cost_usd=float(totals["cost"])),
        by_principal=[
            UsageByPrincipal(
                principal=PrincipalRef(id=r["id"], name=r["name"]), requests=r["requests"],
                tokens=int(r["tokens"]), cost_usd=float(r["cost"]),
            )
            for r in by_principal
        ],
        by_day=[
            UsageByDay(date=r["day"], requests=r["requests"], tokens=int(r["tokens"]), cost_usd=float(r["cost"]))
            for r in by_day
        ],
        denied=DeniedCounts(rate=denied["rate"], budget=denied["budget"], policy=denied["policy"]),
    )


# ------------------------------------------------------------------ requests: decisions grouped by request id

_GROUPED = """
    SELECT d.request_id,
           min(d.created_at) AS started_at,
           count(*) AS checks,
           bool_or(d.outcome = 'deny') AS denied,
           (bool_and(d.action IN ('audit.read', 'analytics.read')) AND NOT bool_or(d.outcome = 'deny')) AS console_only,
           (array_agg(d.principal_id ORDER BY d.created_at, d.id) FILTER (WHERE d.principal_id IS NOT NULL))[1] AS principal_id,
           max(d.policy_version) AS policy_version,
           (array_agg(d.stage ORDER BY d.created_at, d.id) FILTER (WHERE d.outcome = 'deny'))[1] AS deny_stage,
           (array_agg(d.reason ORDER BY d.created_at, d.id) FILTER (WHERE d.outcome = 'deny'))[1] AS deny_reason,
           (array_agg(d.action ORDER BY d.created_at, d.id) FILTER (WHERE d.outcome = 'deny'))[1] AS deny_action,
           (array_agg(d.resource ORDER BY d.created_at, d.id) FILTER (WHERE d.outcome = 'deny'))[1] AS deny_resource
    FROM gateway_decisions d
    GROUP BY d.request_id
"""


def _request_summary(row: DbRecord, name: str | None) -> RequestSummary:
    principal = PrincipalRef(id=row["principal_id"], name=name) if row["principal_id"] is not None else None
    first_deny = None
    if row["denied"]:
        first_deny = FirstDeny(
            stage=row["deny_stage"], reason=row["deny_reason"], action=row["deny_action"], resource=row["deny_resource"],
        )
    return RequestSummary(
        request_id=row["request_id"], started_at=row["started_at"], principal=principal, checks=row["checks"],
        outcome="deny" if row["denied"] else "allow", first_deny=first_deny, policy_version=row["policy_version"],
    )


@router.get("/overview", response_model=Overview)
async def overview(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to look back"),
    include_console_reads: bool = Query(default=False, description="Also count requests made only of console reads"),
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> Overview:
    """Requests checked and blocked in the window, the top deny reasons and today's token budget.

    It counts requests (decisions grouped by request id), so the numbers match the request list. A request is
    blocked when any of its decisions was a deny. Requests made only of allowed console reads (`audit.read`,
    `analytics.read`) are left out unless `include_console_reads` is true. A denied console read is never left out.
    """
    await _read(ctx, "overview")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    keep = "" if include_console_reads else " AND NOT console_only"
    async with tenant_connection(pool, principal.tenant_id) as conn:
        rows = await conn.fetch(
            f"SELECT (started_at AT TIME ZONE 'UTC')::date AS day, count(*) AS checked, "
            f"count(*) FILTER (WHERE denied) AS blocked FROM ({_GROUPED}) g WHERE started_at >= $1{keep} GROUP BY 1 ORDER BY 1",
            since,
        )
        reasons = await conn.fetch(
            f"SELECT deny_reason AS reason, count(*) AS count FROM ({_GROUPED}) g WHERE denied AND started_at >= $1{keep} "
            f"GROUP BY deny_reason ORDER BY count DESC, deny_reason LIMIT 5",
            since,
        )
    try:
        used = await read_budget_used(ctx.runtime, principal.tenant_id)
    except DependencyUnavailable:
        raise HTTPException(
            status_code=503,
            detail={"error": "dependency_unavailable", "reason": "A required service is unavailable. Try again shortly."},
        ) from None
    checked = sum(r["checked"] for r in rows)
    blocked = sum(r["blocked"] for r in rows)
    return Overview(
        days=days, checked=checked, blocked=blocked, deny_rate=(blocked / checked) if checked else 0.0,
        budget=OverviewBudget(used_tokens=used, limit_tokens=config.DEFAULT_DAILY_TOKEN_BUDGET, period="day"),
        top_deny_reasons=[DenyReasonCount(reason=r["reason"], count=r["count"]) for r in reasons],
        by_day=[OverviewDay(date=r["day"], checked=r["checked"], blocked=r["blocked"]) for r in rows],
    )


@router.get("/requests", response_model=RequestPage)
async def list_requests(
    outcome: Literal["allow", "deny"] | None = None,
    action: str | None = Query(default=None, description="Only requests with a decision of this action"),
    by_principal: UUID | None = Query(default=None, alias="principal", description="Only requests of this principal id"),
    policy_version: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    include_console_reads: bool = Query(default=False, description="Also list requests made only of console reads"),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> RequestPage:
    """Decisions grouped by request id, newest request first, with filters and a keyset cursor.

    A request is a deny when any of its decisions was a deny. `since` and `until` apply to the time of the
    first decision of the request. Requests made only of allowed console reads (`audit.read`, `analytics.read`)
    are left out unless `include_console_reads` is true. A denied console read is never left out.
    """
    await _read(ctx, "requests")
    conditions: list[str] = [] if include_console_reads else ["NOT g.console_only"]
    args: list[Any] = []

    def add(sql: str, value: Any) -> None:
        args.append(value)
        conditions.append(sql.format(n=len(args)))

    if outcome == "deny":
        conditions.append("g.denied")
    elif outcome == "allow":
        conditions.append("NOT g.denied")
    if action is not None:
        add("g.request_id IN (SELECT request_id FROM gateway_decisions WHERE action = ${n})", action)
    if by_principal is not None:
        add("g.request_id IN (SELECT request_id FROM gateway_decisions WHERE principal_id = ${n})", by_principal)
    if policy_version is not None:
        add("g.policy_version = ${n}", policy_version)
    if since is not None:
        add("g.started_at >= ${n}", since)
    if until is not None:
        add("g.started_at <= ${n}", until)
    if cursor is not None:
        try:
            stamp, key = decode_key_cursor(cursor)
        except InvalidCursor:
            raise HTTPException(status_code=400, detail={"error": "invalid_cursor", "reason": "The cursor is not valid"}) from None
        args.extend([stamp, key])
        conditions.append(f"(g.started_at, g.request_id) < (${len(args) - 1}, ${len(args)})")
    args.append(limit + 1)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = (
        f"SELECT g.*, p.name AS principal_name FROM ({_GROUPED}) g LEFT JOIN principals p ON p.id = g.principal_id "
        f"{where} ORDER BY g.started_at DESC, g.request_id DESC LIMIT ${len(args)}"
    )
    async with tenant_connection(pool, principal.tenant_id) as conn:
        rows = await conn.fetch(sql, *args)
    page = rows[:limit]
    next_cursor = encode_key_cursor(page[-1]["started_at"], page[-1]["request_id"]) if len(rows) > limit else None
    return RequestPage(items=[_request_summary(r, r["principal_name"]) for r in page], next_cursor=next_cursor)


@router.get("/requests/{request_id}", response_model=RequestDetail)
async def get_request(
    request: Request,
    request_id: str,
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> RequestDetail:
    """One request with its decisions, oldest first. A foreign id and a missing id give the same 404."""
    await _read(ctx, "requests")
    async with tenant_connection(pool, principal.tenant_id) as conn:
        rows = await conn.fetch(
            f"SELECT {_DECISION_COLUMNS} {_DECISION_FROM} WHERE d.request_id = $1 "
            f"ORDER BY d.created_at ASC, d.id ASC LIMIT {TRACE_CAP}",
            request_id,
        )
        if not rows:
            raise _not_found("Request")
        head = await conn.fetchrow(
            "SELECT min(created_at) AS started_at, bool_or(outcome = 'deny') AS denied, max(policy_version) AS policy_version, "
            "(array_agg(principal_id ORDER BY created_at, id) FILTER (WHERE principal_id IS NOT NULL))[1] AS principal_id "
            "FROM gateway_decisions WHERE request_id = $1", request_id,
        )
        tenant = await conn.fetchrow("SELECT id, slug FROM tenants WHERE id = $1", principal.tenant_id)
        who = None
        if head is not None and head["principal_id"] is not None:
            who = await conn.fetchrow("SELECT id, name FROM principals WHERE id = $1", head["principal_id"])
    if head is None or tenant is None:
        raise _not_found("Request")
    return RequestDetail(
        request_id=request_id, started_at=head["started_at"],
        principal=PrincipalRef(id=who["id"], name=who["name"]) if who is not None else None,
        tenant=TenantRef(id=tenant["id"], slug=tenant["slug"]), policy_version=head["policy_version"],
        outcome="deny" if head["denied"] else "allow",
        decisions=await with_run_status(pool, principal.tenant_id, [_summary(r) for r in rows]),
    )


@router.get("/reason-codes", response_model=list[ReasonCode])
async def reason_codes(
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> list[ReasonCode]:
    """The plain-language catalogue of every reason code. It holds no tenant data."""
    await _read(ctx, "reason-codes")
    return [
        ReasonCode(code=r.code, title=r.title, sentence=r.sentence, policy_field=r.policy_field, stage=r.stage)
        for r in all_reasons()
    ]

"""Trust: the summary of retention and the eval gate (`audit:read`), and the Prometheus endpoint (Sprint 008).

`/metrics` is outside `/v1` because Prometheus expects it there. It is open when `METRICS_PUBLIC` is true (the default
in local mode) and otherwise needs a credential with the `admin` scope: the auth middleware resolves the credential
and this route checks the scope. It carries counts and timings only, never a tenant, a principal or any text.
"""
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from api.auth import require_scope
from api.gateway_deps import gateway_context
from api.models.trust import EvalGate, TrustSummary
from api.routers.console import get_db_pool
from core.database.tenant import DbPool, DbRecord, tenant_connection
from core.identity.models import Principal, Scope
from core.metrics import CONTENT_TYPE, get_metrics
from core.settings import get_settings
from gateway import Action, ActionKind, EnforcementContext, require

router = APIRouter(tags=["trust"])
metrics_router = APIRouter(tags=["trust"])

EVAL_HISTORY = 20


def _scores(value: Any) -> dict[str, float]:
    data = json.loads(value) if isinstance(value, str) else value
    return {str(k): float(v) for k, v in (data or {}).items()}


def _gate(row: DbRecord) -> EvalGate:
    return EvalGate(
        status="passed" if row["passed"] else "failed", baseline=_scores(row["baseline"]), latest=_scores(row["scores"]),
        run_at=row["run_at"],
    )


@router.get("/trust/summary", response_model=TrustSummary)
async def trust_summary(
    pool: DbPool = Depends(get_db_pool),
    principal: Principal = Depends(require_scope(Scope.AUDIT_READ)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> TrustSummary:
    """How long decisions are kept, the oldest one and the last purge, the eval gate and where the metrics are."""
    await require(ctx, Action(ActionKind.AUDIT_READ, resource="trust"))
    settings = get_settings()
    async with tenant_connection(pool, principal.tenant_id) as conn:
        tenant = await conn.fetchrow("SELECT retention_days FROM tenants WHERE id = $1", principal.tenant_id)
        oldest = await conn.fetchval("SELECT MIN(created_at) FROM gateway_decisions")
        last_purge = await conn.fetchval("SELECT MAX(created_at) FROM chain_checkpoints WHERE reason = 'purge'")
        runs = await conn.fetch("SELECT passed, baseline, scores, run_at FROM eval_runs ORDER BY run_at DESC LIMIT $1", EVAL_HISTORY)
    own = None if tenant is None else tenant["retention_days"]
    history = [_gate(r) for r in runs]
    return TrustSummary(
        retention_days=int(own) if own is not None else settings.decision_retention_days,
        retention_is_default=own is None, oldest_decision_at=oldest, last_purge_at=last_purge,
        eval_gate=history[0] if history else None, eval_history=history,
        metrics_public=bool(settings.metrics_public), grafana_url=settings.grafana_url,
    )


@metrics_router.get("/metrics", response_class=Response, responses={200: {"content": {"text/plain": {}}}})
async def metrics(request: Request) -> Response:
    """Prometheus text format: request counts and latency per route, decisions per outcome, jobs per status and the
    outbox lag. Open when `METRICS_PUBLIC` is true, otherwise it needs the `admin` scope."""
    if not get_settings().metrics_public:
        principal: Principal | None = getattr(request.state, "principal", None)
        if principal is None or not principal.has_scope(Scope.ADMIN):
            raise HTTPException(status_code=403, detail="Missing required scope: admin")
    collector = get_metrics()
    await collector.refresh_from_database(request.app.state.db_pool)
    return Response(content=collector.render(), media_type=CONTENT_TYPE)

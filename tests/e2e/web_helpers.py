"""Helpers for the web edge and console tests: extra keys, decision rows and usage rows written as the owner."""
import json
from datetime import datetime, timezone
from uuid import UUID

from core.identity.admin import admin_connection, create_key
from core.settings import get_settings


def key_with(dsn: str, tenant, scopes: list[str]):
    """A new key for the tenant's service principal. Returns (token, prefix)."""
    with admin_connection(dsn) as conn:
        key = create_key(conn, UUID(tenant.principal_id), scopes)
    return key.token, key.prefix


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def secret_of(token: str) -> str:
    return token.split("_", 2)[2]


async def insert_decision(
    pool, tenant, *, created_at: datetime | None = None, request_id: str = "req-x", action: str = "kb.read",
    resource: str | None = "legal", outcome: str = "allow", stage: str = "allow", reason: str = "allowed",
    policy_version: int | None = None, principal_id: str | None = "own", input_hash: str | None = None,
) -> UUID:
    who = tenant.principal_id if principal_id == "own" else principal_id
    return await pool.fetchval(
        "INSERT INTO gateway_decisions (tenant_id, principal_id, request_id, trace_id, action, resource, outcome, stage, "
        "reason, policy_version, input_hash, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING id",
        UUID(tenant.id), UUID(who) if who else None, request_id, "t" * 32, action, resource, outcome, stage, reason,
        policy_version, input_hash, created_at or datetime.now(timezone.utc),
    )


async def insert_usage(pool, tenant, request_id: str, created_at: datetime, prompt=10, completion=5, cost="0.001"):
    await pool.execute(
        "INSERT INTO usage_log (tenant_id, request_id, endpoint, namespace, model, prompt_tokens, completion_tokens, cost_usd, created_at) "
        "VALUES ($1,$2,'/v1/search','legal','m',$3,$4,$5,$6)",
        UUID(tenant.id), request_id, prompt, completion, cost, created_at,
    )


def edge_settings_override(app, **changes):
    """Replace the web edge settings of `app` (mode, preview principal) for one test."""
    from api.web_edge.routes import edge_settings

    patched = get_settings().model_copy(update=changes)
    app.dependency_overrides[edge_settings] = lambda: patched
    return patched


def as_json(text: str):
    return json.loads(text)

"""The decision record: one `gateway_decisions` row per `enforce()` call, allow or deny.

Writes go through `tenant_connection`, so row-level security applies. The row holds the SHA-256 of the input
and never the text. A failed write raises; `enforce()` then turns an allow into a deny `decision_unrecorded`
(fail closed, strict rules 3 and 10). A deny stays a deny.
"""
from core.database.tenant import tenant_connection
from gateway.types import Action, Decision, EnforcementContext

_INSERT = """
INSERT INTO gateway_decisions
    (tenant_id, principal_id, request_id, trace_id, action, resource, outcome, stage, reason, policy_version, input_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
"""


async def write_decision(ctx: EnforcementContext, action: Action, decision: Decision) -> None:
    """Insert the row. Raises when it cannot: `enforce()` turns a failed write on an allow into a deny."""
    tenant_id = ctx.principal.tenant_id if ctx.principal else ctx.boundary.tenant_id
    if tenant_id is None:
        raise RuntimeError("no tenant to record the decision under")
    async with tenant_connection(ctx.runtime.pool, tenant_id) as conn:
        await conn.execute(
            _INSERT,
            tenant_id,
            ctx.principal.id if ctx.principal else None,
            ctx.request_id,
            ctx.trace_id,
            action.kind.value,
            action.resource,
            "allow" if decision.allowed else "deny",
            decision.stage,
            decision.reason,
            decision.policy_version,
            action.input_hash,
        )

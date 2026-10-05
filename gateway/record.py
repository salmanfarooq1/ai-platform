"""The decision record: one `gateway_decisions` row per `enforce()` call, allow or deny.

Writes go through `tenant_connection`, so row-level security applies. The row holds the SHA-256 of the input
and never the text. A failed write raises; `enforce()` then turns an allow into a deny `decision_unrecorded`
(fail closed, strict rules 3 and 10). A deny stays a deny.

A decision row is never lost because of the bus. The publish of an allow is inside the transaction, so a bus
error rolls the row back and the allow fails closed. The publish of a deny runs in a savepoint: a bus error
rolls back only the publish, the row is committed and the error is logged (ADR-0006, ADR-0008).
"""
import logging
from uuid import UUID

from core.database.tenant import tenant_connection
from gateway.types import Action, Decision, EnforcementContext
from ports import DECISION_RECORDED, CloudEvent

logger = logging.getLogger("gateway.record")

EVENT_SOURCE = "/gateway"

_INSERT = """
INSERT INTO gateway_decisions
    (tenant_id, principal_id, request_id, trace_id, action, resource, outcome, stage, reason, policy_version, input_hash,
     execution_id)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
RETURNING id
"""


def decision_event(
    decision_id: UUID, tenant_id: UUID, ctx: EnforcementContext, action: Action, decision: Decision
) -> CloudEvent:
    """The `platform.gateway.decision.v1` event. The payload carries the decision id and verdict and never the
    input text (nor its hash): a subscriber that needs more reads the decision row under row-level security."""
    return CloudEvent(
        type=DECISION_RECORDED,
        source=EVENT_SOURCE,
        subject=str(decision_id),
        tenantid=str(tenant_id),
        data={
            "decision_id": str(decision_id),
            "outcome": "allow" if decision.allowed else "deny",
            "stage": decision.stage,
            "reason": decision.reason,
            "action": action.kind.value,
            "resource": action.resource,
            "request_id": ctx.request_id,
            "execution_id": str(ctx.execution_id) if ctx.execution_id else None,
        },
    )


async def write_decision(ctx: EnforcementContext, action: Action, decision: Decision) -> UUID | None:
    """Insert the row, then publish one event for it, inside the same transaction (so an outbox subscriber
    commits with the decision). Returns the decision id. Raises when it cannot write, or when it cannot publish
    an allow: `enforce()` turns a failed record on an allow into a deny. A failed publish on a deny is logged
    and does not lose the row."""
    tenant_id = ctx.principal.tenant_id if ctx.principal else ctx.boundary.tenant_id
    if tenant_id is None:
        raise RuntimeError("no tenant to record the decision under")
    async with tenant_connection(ctx.runtime.pool, tenant_id) as conn:
        decision_id: UUID = await conn.fetchval(
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
            ctx.execution_id,
        )
        events = ctx.runtime.events
        if events is not None:
            event = decision_event(decision_id, tenant_id, ctx, action, decision)
            if decision.allowed:
                await events.publish(event, tx=conn)  # a failure rolls the row back: the allow fails closed
            else:
                try:
                    async with conn.transaction():  # a savepoint: a failed publish leaves the deny row alone
                        await events.publish(event, tx=conn)
                except Exception:
                    logger.error("decision event not published, deny row kept: decision_id=%s", decision_id, exc_info=True)
    return decision_id

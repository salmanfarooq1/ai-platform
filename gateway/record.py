"""The decision record: one `gateway_decisions` row per `enforce()` call, allow or deny.

Writes go through `tenant_connection`, so row-level security applies. The row holds the SHA-256 of the input
and never the text. A failed write raises; `enforce()` then turns an allow into a deny `decision_unrecorded`
(fail closed, strict rules 3 and 10). A deny stays a deny.

A decision row is never lost because of the bus. The publish of an allow is inside the transaction, so a bus
error rolls the row back and the allow fails closed. The publish of a deny runs in a savepoint: a bus error
rolls back only the publish, the row is committed and the error is logged (ADR-0006, ADR-0008).
"""
import logging
from typing import Any
from uuid import UUID, uuid4

from core.database.tenant import DbConnection, tenant_connection
from core.metrics import get_metrics
from gateway import chain
from gateway.types import Action, Decision, EnforcementContext
from ports import DECISION_RECORDED, CloudEvent

logger = logging.getLogger("gateway.record")

EVENT_SOURCE = "/gateway"

_COLUMNS = (
    "id, tenant_id, principal_id, request_id, trace_id, action, resource, outcome, stage, reason, policy_version, "
    "input_hash, execution_id"
)

_INSERT_PLAIN = f"""
INSERT INTO gateway_decisions ({_COLUMNS})
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
"""

_INSERT_CHAINED = f"""
INSERT INTO gateway_decisions ({_COLUMNS}, created_at, chain_position, prev_hash, row_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
"""

# One writer per tenant at a time: the lock is held to the end of the transaction, so links are taken in order.
_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended('decision_chain:' || $1::text, 0))"
_HEAD = "SELECT position, row_hash, clock_timestamp() AS now FROM chain_heads WHERE tenant_id = $1"
_NEW_HEAD = "INSERT INTO chain_heads (tenant_id, position, row_hash) VALUES ($1, 0, $2) ON CONFLICT DO NOTHING"
_MOVE_HEAD = "UPDATE chain_heads SET position = $2, row_hash = $3, updated_at = NOW() WHERE tenant_id = $1"


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


async def _insert_chained(conn: DbConnection, tenant_id: UUID, decision_id: UUID, values: tuple[Any, ...]) -> None:
    """Take the next link of the tenant's chain and insert the row with it. The time of the row is read from the
    database after the lock is held, so it never goes backwards along the chain."""
    await conn.execute(_LOCK, str(tenant_id))
    head = await conn.fetchrow(_HEAD, tenant_id)
    if head is None:  # a tenant created after migration 0009: its chain starts here
        genesis = chain.genesis_hash(tenant_id)
        await conn.execute(_NEW_HEAD, tenant_id, genesis)  # the genesis hash is derived, so it needs no checkpoint row
        head = await conn.fetchrow(_HEAD, tenant_id)
        if head is None:
            raise RuntimeError("chain head missing after it was created")
    position = int(head["position"]) + 1
    prev_hash = str(head["row_hash"])
    created_at = head["now"]
    (_id, _tenant, principal_id, request_id, _trace, action, resource, outcome, stage, reason, policy_version,
     input_hash, execution_id) = values
    record = chain.decision_record(
        id=decision_id, tenant_id=tenant_id, principal_id=principal_id, request_id=request_id, action=action,
        resource=resource, outcome=outcome, stage=stage, reason=reason, policy_version=policy_version,
        input_sha256=input_hash, execution_id=execution_id, created_at=created_at,
    )
    row_hash = chain.compute_row_hash(record, prev_hash)
    await conn.execute(_INSERT_CHAINED, *values, created_at, position, prev_hash, row_hash)
    await conn.execute(_MOVE_HEAD, tenant_id, position, row_hash)


async def write_decision(ctx: EnforcementContext, action: Action, decision: Decision) -> UUID | None:
    """Insert the row, then publish one event for it, inside the same transaction (so an outbox subscriber
    commits with the decision). Returns the decision id. Raises when it cannot write, or when it cannot publish
    an allow: `enforce()` turns a failed record on an allow into a deny. A failed publish on a deny is logged
    and does not lose the row."""
    tenant_id = ctx.principal.tenant_id if ctx.principal else ctx.boundary.tenant_id
    if tenant_id is None:
        raise RuntimeError("no tenant to record the decision under")
    decision_id = uuid4()
    values = (
        decision_id,
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
    async with tenant_connection(ctx.runtime.pool, tenant_id) as conn:
        if decision.allowed:
            await _insert_chained(conn, tenant_id, decision_id, values)  # a failure fails the allow closed
        else:
            try:
                async with conn.transaction():  # a savepoint: a failed chain step leaves no half-written link
                    await _insert_chained(conn, tenant_id, decision_id, values)
            except Exception:
                # A deny keeps its row even when the chain step fails. The row is stored without a link and says so
                # (null hashes), so a receipt for it is refused and the purge still ages it out.
                logger.error("decision chain step failed, deny row kept unchained: decision_id=%s", decision_id, exc_info=True)
                await conn.execute(_INSERT_PLAIN, *values)
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
    get_metrics().count_decision(action.kind.value, "allow" if decision.allowed else "deny", decision.stage)
    return decision_id

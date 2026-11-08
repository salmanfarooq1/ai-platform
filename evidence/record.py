"""Persist versioned decision evidence with the decision, chain and event in one transaction."""
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from core.database.tenant import DbConnection, DbPool, tenant_connection
from core.metrics import get_metrics
from evidence import chain
from evidence.extensions import validate_extensions
from ports import DECISION_RECORDED, CloudEvent, DecisionEntry, EventBus

logger = logging.getLogger("evidence.record")
_COLUMNS = ("id, tenant_id, principal_id, request_id, trace_id, action, resource, outcome, stage, reason, "
            "policy_version, input_hash, execution_id, record_version, extensions")
_INSERT_PLAIN = f"INSERT INTO gateway_decisions ({_COLUMNS}) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)"
_INSERT_CHAINED = f"INSERT INTO gateway_decisions ({_COLUMNS}, created_at, chain_position, prev_hash, row_hash) VALUES " \
                  "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb,$16,$17,$18,$19)"
_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended('decision_chain:' || $1::text, 0))"
_HEAD = "SELECT position, row_hash, clock_timestamp() AS now FROM chain_heads WHERE tenant_id = $1"
_NEW_HEAD = "INSERT INTO chain_heads (tenant_id, position, row_hash) VALUES ($1, 0, $2) ON CONFLICT DO NOTHING"
_MOVE_HEAD = "UPDATE chain_heads SET position = $2, row_hash = $3, updated_at = NOW() WHERE tenant_id = $1"


def decision_event(entry: DecisionEntry, decision_id: UUID) -> CloudEvent:
    """Build the privacy-safe event; its body never contains input or its hash."""
    return CloudEvent(
        type=DECISION_RECORDED, source="/gateway", subject=str(decision_id), tenantid=str(entry.tenant_id),
        data={"decision_id": str(decision_id), "outcome": entry.outcome, "stage": entry.stage,
              "reason": entry.reason, "action": entry.action, "resource": entry.resource,
              "request_id": entry.request_id,
              "execution_id": str(entry.execution_id) if entry.execution_id else None},
    )


async def _insert_chained(conn: DbConnection, entry: DecisionEntry, decision_id: UUID,
                          extensions: dict[str, Any], values: tuple[Any, ...]) -> None:
    await conn.execute(_LOCK, str(entry.tenant_id))
    head = await conn.fetchrow(_HEAD, entry.tenant_id)
    if head is None:
        await conn.execute(_NEW_HEAD, entry.tenant_id, chain.genesis_hash(entry.tenant_id))
        head = await conn.fetchrow(_HEAD, entry.tenant_id)
        if head is None:
            raise RuntimeError("chain head missing after it was created")
    position = int(head["position"]) + 1
    prev_hash = str(head["row_hash"])
    created_at = head["now"]
    record = chain.decision_record(
        id=decision_id, tenant_id=entry.tenant_id, principal_id=entry.principal_id,
        request_id=entry.request_id, action=entry.action, resource=entry.resource, outcome=entry.outcome,
        stage=entry.stage, reason=entry.reason, policy_version=entry.policy_version,
        input_sha256=entry.input_sha256, execution_id=entry.execution_id, created_at=created_at,
        record_version=2, extensions=extensions,
    )
    row_hash = chain.compute_row_hash(record, prev_hash)
    await conn.execute(_INSERT_CHAINED, *values, created_at, position, prev_hash, row_hash)
    await conn.execute(_MOVE_HEAD, entry.tenant_id, position, row_hash)


async def write_decision(pool: DbPool, entry: DecisionEntry, events: EventBus | None = None) -> UUID:
    """Write a v2 record. An allow fails closed on row/chain/event failure; a deny row survives publish failure."""
    extensions = validate_extensions(entry.extensions)
    decision_id = uuid4()
    encoded = json.dumps(extensions, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    values = (decision_id, entry.tenant_id, entry.principal_id, entry.request_id, entry.trace_id, entry.action,
              entry.resource, entry.outcome, entry.stage, entry.reason, entry.policy_version, entry.input_sha256,
              entry.execution_id, 2, encoded)
    async with tenant_connection(pool, entry.tenant_id) as conn:
        if entry.outcome == "allow":
            await _insert_chained(conn, entry, decision_id, extensions, values)
        else:
            try:
                async with conn.transaction():
                    await _insert_chained(conn, entry, decision_id, extensions, values)
            except Exception:
                logger.error("decision chain step failed, deny row kept unchained: decision_id=%s", decision_id, exc_info=True)
                await conn.execute(_INSERT_PLAIN, *values)
        if events is not None:
            event = decision_event(entry, decision_id)
            if entry.outcome == "allow":
                await events.publish(event, tx=conn)
            else:
                try:
                    async with conn.transaction():
                        await events.publish(event, tx=conn)
                except Exception:
                    logger.error("decision event not published, deny row kept: decision_id=%s", decision_id, exc_info=True)
    get_metrics().count_decision(entry.action, entry.outcome, entry.stage)
    return decision_id

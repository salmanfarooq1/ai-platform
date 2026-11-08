"""Postgres adapters for always-on decision recording and receipt lookup."""
from uuid import UUID

from core.database.tenant import DbPool, tenant_connection
from evidence import record
from ports import DecisionEntry, EventBus, EvidenceRef


class PgDecisionSink:
    """Required production sink; rows are written by the evidence package."""

    def __init__(self, pool: DbPool) -> None:
        self._pool = pool

    async def write(self, entry: DecisionEntry, events: EventBus | None = None) -> UUID:
        return await record.write_decision(self._pool, entry, events)


class PgEvidenceLookup:
    """Tenant-scoped lookup for receipts; absent and foreign ids are indistinguishable."""

    def __init__(self, pool: DbPool) -> None:
        self._pool = pool

    async def decision(self, tenant_id: UUID, decision_id: UUID) -> EvidenceRef:
        async with tenant_connection(self._pool, tenant_id) as conn:
            row = await conn.fetchrow("SELECT id FROM gateway_decisions WHERE id = $1", decision_id)
        if row is None:
            return EvidenceRef(linked=False)
        return EvidenceRef(linked=True, decision_id=decision_id, href=f"/v1/receipts/{decision_id}")

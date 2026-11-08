"""Shared tenant-scoped EvidenceLookup contract for fixture and Postgres adapters."""
from uuid import UUID, uuid4

import pytest

from adapters.pg_evidence import PgDecisionSink, PgEvidenceLookup
from ports import DecisionEntry, EvidenceLookup, EvidenceRef


class ContractLookup:
    """No-op lookup allowed only as a contract fixture; production always uses PgEvidenceLookup."""

    async def decision(self, tenant_id: UUID, decision_id: UUID) -> EvidenceRef:
        del tenant_id, decision_id
        return EvidenceRef(linked=False)


@pytest.fixture(params=["contract-noop", "postgres"])
def evidence_lookup(request, db_pool) -> EvidenceLookup:
    return ContractLookup() if request.param == "contract-noop" else PgEvidenceLookup(db_pool)


async def test_unknown_and_foreign_ids_have_the_same_unlinked_shape(evidence_lookup: EvidenceLookup, db_pool, tenant_a, tenant_b) -> None:
    decision_id = uuid4()
    if isinstance(evidence_lookup, PgEvidenceLookup):
        entry = DecisionEntry(
            UUID(tenant_b.id), None, "foreign", "trace", "system.read", "system/modules", "allow", "allow",
            "allowed", None, None, None, {},
        )
        decision_id = await PgDecisionSink(db_pool).write(entry)
    missing = await evidence_lookup.decision(UUID(tenant_a.id), uuid4())
    foreign = await evidence_lookup.decision(UUID(tenant_a.id), decision_id)
    assert missing == foreign == EvidenceRef(linked=False)


async def test_linked_reference_returns_an_existing_decision(evidence_lookup: EvidenceLookup, db_pool, tenant_a) -> None:
    if isinstance(evidence_lookup, PgEvidenceLookup):
        entry = DecisionEntry(
            UUID(tenant_a.id), None, "linked", "trace", "system.read", "system/modules", "allow", "allow",
            "allowed", None, None, None, {},
        )
        decision_id = await PgDecisionSink(db_pool).write(entry)
        ref = await evidence_lookup.decision(UUID(tenant_a.id), decision_id)
        assert ref == EvidenceRef(linked=True, decision_id=decision_id, href=f"/v1/receipts/{decision_id}")
    else:
        assert await evidence_lookup.decision(UUID(tenant_a.id), uuid4()) == EvidenceRef(linked=False)

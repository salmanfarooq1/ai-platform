"""Shared DecisionSink contract for the in-memory fixture and real Postgres adapter."""
import json
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from adapters.pg_evidence import PgDecisionSink
from core.database.tenant import tenant_connection
from ports import DecisionEntry, DecisionSink, EventBus


@dataclass
class RecordingDecisionSink:
    """Successful in-memory test double; never used in production composition."""

    entries: list[DecisionEntry] = field(default_factory=list)

    async def write(self, entry: DecisionEntry, events: EventBus | None = None) -> UUID:
        self.entries.append(entry)
        return uuid4()


@pytest.fixture(params=["contract-fake", "postgres"])
def decision_sink(request, db_pool) -> DecisionSink:
    return RecordingDecisionSink() if request.param == "contract-fake" else PgDecisionSink(db_pool)


def entry(tenant_id: UUID) -> DecisionEntry:
    return DecisionEntry(
        tenant_id=tenant_id, principal_id=None, request_id="req-1", trace_id="trace-1", action="system.read",
        resource="system/modules", outcome="allow", stage="allow", reason="allowed", policy_version=None,
        input_sha256=None, execution_id=None, extensions={},
    )


async def test_write_returns_a_decision_id_and_keeps_the_exact_entry(decision_sink: DecisionSink, tenant_a, db_pool) -> None:
    value = entry(UUID(tenant_a.id))
    decision_id = await decision_sink.write(value)
    assert isinstance(decision_id, UUID)
    if isinstance(decision_sink, RecordingDecisionSink):
        assert decision_sink.entries == [value]
    else:
        async with tenant_connection(db_pool, value.tenant_id) as conn:
            row = await conn.fetchrow("SELECT record_version, extensions FROM gateway_decisions WHERE id = $1", decision_id)
        assert row is not None and row["record_version"] == 2
        assert json.loads(row["extensions"]) == {}


async def test_event_bus_is_an_optional_write_argument(decision_sink: DecisionSink, tenant_a) -> None:
    decision_id = await decision_sink.write(entry(UUID(tenant_a.id)), events=None)
    assert isinstance(decision_id, UUID)


async def test_sink_write_failure_is_propagated() -> None:
    class FailingSink:
        async def write(self, entry: DecisionEntry, events: EventBus | None = None) -> UUID:
            raise OSError("sink unavailable")

    with pytest.raises(OSError, match="sink unavailable"):
        await FailingSink().write(entry(uuid4()))

"""Sprint 010 A2 and A5, through the real app: decisions are written to the outbox in their own transaction, a relay
publishes them to Kafka (killed halfway once), and a consumer group handles each decision event once. Then the
platform goes back to `EVENT_BUS=outbox` with the same tables."""
import json
from collections import Counter

import pytest

from adapters.kafka_event_bus import topic_for
from adapters.pg_outbox_events import OutboxRelay
from ports import DECISION_RECORDED
from tests.fakes import FakeEventBus
from tests.integration.test_kafka_bus import Crash, CrashingTarget
from tests.kafka_helpers import BACKEND, make_bus, pump, read_all


@pytest.fixture(params=[BACKEND])
def backend(request):
    return request.param


async def make_decisions(client, pool, n=6):
    for _ in range(n):
        assert (await client.get("/v1/jobs")).status_code == 200
    return {str(r["id"]) for r in await pool.fetch("SELECT id FROM gateway_decisions")}


async def test_a_decision_row_leads_to_exactly_one_consumed_event_even_when_the_relay_dies_mid_batch(
    backend, app, client, pool, fake_llm, fake_embeddings,
):
    decisions = await make_decisions(client, pool)
    assert len(decisions) >= 4 and await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL") >= len(decisions)

    producer, broker = make_bus()
    consumer, _ = make_bus(pool=app.state.db_pool, broker=broker)
    try:
        with pytest.raises(Crash):
            await OutboxRelay(app.state.db_pool, CrashingTarget(producer, after=3), batch_size=100).run_once()
        assert await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL") > 0
        while await OutboxRelay(app.state.db_pool, producer, batch_size=100).run_once():
            pass
        assert await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL") == 0

        handled = Counter()

        async def handler(ev, tx):
            handled[ev.data["decision_id"]] += 1

        consumer.consume(DECISION_RECORDED, handler, name="e2e")
        # Every decision, including those the requests above and the relay's own queries wrote, is consumed.
        all_ids = {str(r["id"]) for r in await pool.fetch("SELECT id FROM gateway_decisions")}
        await pump(consumer, lambda: set(handled) >= all_ids, timeout=60)
        for _ in range(5):
            await consumer.poll_once(0.2)
        assert set(handled.values()) == {1}  # one per decision after dedupe, though one event was sent twice
        records = await read_all(topic_for(DECISION_RECORDED), broker, len(all_ids) + 1)
        ids = Counter(dict(r.headers)["ce_id"] for r in records)
        assert max(ids.values()) == 2 and len(ids) >= len(all_ids)  # the duplicate really reached Kafka
        for r in records:
            assert "input" not in json.loads(r.value)  # no input text on the bus
    finally:
        await producer.close()
        await consumer.close()


async def test_switching_back_to_outbox_needs_no_data_migration(app, client, pool, fake_llm, fake_embeddings):
    """Rows written while EVENT_BUS=kafka are ordinary outbox rows. With EVENT_BUS=outbox the same relay code sends the
    ones Kafka never got to the in-process target, and the schema has not changed."""
    from adapters.registry import PORT_NAMES, build_adapters
    from core.settings import Settings

    await make_decisions(client, pool, n=2)
    before = await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL")
    assert before > 0
    overrides = {name: object() for name in PORT_NAMES if name != "events"}
    for mode in ("kafka", "outbox"):
        s = Settings(mode="local", event_bus=mode, kafka_bootstrap="broker:9092")
        assert type(build_adapters(s, pool=app.state.db_pool, overrides=overrides).events).__name__ == "OutboxEventBus"
    target = FakeEventBus()
    sent = 0
    while True:
        n = await OutboxRelay(app.state.db_pool, target, batch_size=100).run_once()
        if not n:
            break
        sent += n
    assert sent == before and len(target.published) == before
    assert await pool.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL") == 0

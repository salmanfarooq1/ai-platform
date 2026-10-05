"""Sprint 007 A3: the transactional outbox on real Postgres, as the app role. A rolled-back transaction publishes
nothing, the relay is at least once, and a consumer that dedupes by CloudEvent id handles each event once."""
import asyncio
from uuid import UUID

import pytest

from adapters.pg_outbox_events import IdempotentConsumer, OutboxEventBus, OutboxRelay
from core.database.tenant import tenant_connection
from ports import CloudEvent
from tests.fakes import FakeEventBus

pytestmark = pytest.mark.asyncio

TYPE = "platform.test.thing.v1"


def make_event(tenant, **data):
    return CloudEvent(type=TYPE, source="/test", subject="s", tenantid=tenant.id, data=data or {"k": "v"})


async def outbox_rows(pool, tenant):
    async with tenant_connection(pool, UUID(tenant.id)) as conn:
        return await conn.fetch("SELECT event_id, published_at, attempts FROM outbox ORDER BY created_at")


class Rollback(Exception):
    pass


async def test_a_rolled_back_transaction_publishes_nothing(db_pool, tenant_a):
    bus, target = OutboxEventBus(db_pool), FakeEventBus()
    ev = make_event(tenant_a)
    with pytest.raises(Rollback):
        async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
            await conn.execute("INSERT INTO feedback (tenant_id, request_id, endpoint, rating) VALUES ($1, 'r', '/v1/search', 'up')", UUID(tenant_a.id))
            await bus.publish(ev, tx=conn)
            raise Rollback  # the state change fails after the publish
    assert await outbox_rows(db_pool, tenant_a) == []
    assert await OutboxRelay(db_pool, target).run_once() == 0 and target.published == []


async def test_a_committed_transaction_publishes_with_its_state_change(db_pool, tenant_a, owner_pool):
    bus = OutboxEventBus(db_pool)
    ev = make_event(tenant_a)
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        await bus.publish(ev, tx=conn)
        assert await owner_pool.fetchval("SELECT count(*) FROM outbox") == 0  # not visible before the commit
    rows = await outbox_rows(db_pool, tenant_a)
    assert [r["event_id"] for r in rows] == [ev.id] and rows[0]["published_at"] is None


async def test_publishing_the_same_event_id_twice_stores_it_once(db_pool, tenant_a):
    bus = OutboxEventBus(db_pool)
    ev = make_event(tenant_a)
    await bus.publish(ev)
    await bus.publish(ev)
    assert len(await outbox_rows(db_pool, tenant_a)) == 1


async def test_the_relay_publishes_each_event_once_and_marks_it_sent(db_pool, tenant_a, tenant_b):
    bus, target = OutboxEventBus(db_pool), FakeEventBus()
    events = [make_event(t, n=i) for i in range(3) for t in (tenant_a, tenant_b)]
    for ev in events:
        await bus.publish(ev)
    relay = OutboxRelay(db_pool, target)
    assert await relay.run_once() == 6
    assert sorted(e.id for e in target.published) == sorted(e.id for e in events)
    assert {e.tenantid for e in target.published} == {tenant_a.id, tenant_b.id}  # across tenants, as the relay has no tenant
    assert await relay.run_once() == 0 and len(target.published) == 6  # sent rows are not sent again
    assert all(r["published_at"] is not None for r in await outbox_rows(db_pool, tenant_a))


async def test_two_relays_at_once_do_not_send_an_event_twice(db_pool, tenant_a):
    bus, target = OutboxEventBus(db_pool), FakeEventBus()
    for i in range(12):
        await bus.publish(make_event(tenant_a, n=i))
    sent = await asyncio.gather(*[OutboxRelay(db_pool, target, batch_size=12).run_once() for _ in range(3)])
    assert sum(sent) == 12 and len(target.published) == 12 and len({e.id for e in target.published}) == 12


async def test_the_relay_is_at_least_once_a_failed_send_is_tried_again(db_pool, tenant_a):
    bus = OutboxEventBus(db_pool)
    ev = make_event(tenant_a)
    await bus.publish(ev)

    class Flaky:
        def __init__(self):
            self.calls = 0
            self.got = []

        def subscribe(self, type, handler):
            pass

        async def publish(self, event, *, tx=None):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("broker down")
            self.got.append(event)

    target = Flaky()
    relay = OutboxRelay(db_pool, target)
    assert await relay.run_once() == 0
    [row] = await outbox_rows(db_pool, tenant_a)
    assert row["published_at"] is None and row["attempts"] == 1  # kept, and counted
    assert await relay.run_once() == 1 and [e.id for e in target.got] == [ev.id]


async def test_a_crash_between_the_send_and_the_mark_sends_again_and_a_consumer_that_dedupes_runs_once(db_pool, tenant_a):
    bus = OutboxEventBus(db_pool)
    ev = make_event(tenant_a)
    await bus.publish(ev)
    handled = []

    async def handler(event, tx):
        handled.append(event.id)

    consumer = IdempotentConsumer("audit-copy", handler, pool=db_pool)
    deliveries = []

    class CrashAfterSend:
        """Delivers to the consumer, then fails before the relay can mark the row (the process died)."""

        def subscribe(self, type, handler):
            pass

        async def publish(self, event, *, tx=None):
            deliveries.append(event.id)
            await consumer(event, None)  # no tx: the consumer commits in a transaction of its own
            if len(deliveries) == 1:
                raise RuntimeError("process died before the mark")

    relay = OutboxRelay(db_pool, CrashAfterSend())
    assert await relay.run_once() == 0  # the mark did not happen
    assert await relay.run_once() == 1  # sent again: at least once
    assert deliveries == [ev.id, ev.id]
    assert handled == [ev.id]  # but the consumer handled it once


async def test_a_consumer_dedupes_across_restarts_through_processed_events(db_pool, tenant_a, tenant_b):
    handled = []

    async def handler(event, tx):
        handled.append(event.id)

    ev = make_event(tenant_a)
    await IdempotentConsumer("c", handler, pool=db_pool)(ev, None)
    await IdempotentConsumer("c", handler, pool=db_pool)(ev, None)  # a new process: empty LRU, same table
    assert handled == [ev.id]
    await IdempotentConsumer("other-consumer", handler, pool=db_pool)(ev, None)  # the id is per consumer
    assert handled == [ev.id, ev.id]
    async with tenant_connection(db_pool, UUID(tenant_b.id)) as conn:  # row-level security: B sees none of A's marks
        assert await conn.fetchval("SELECT count(*) FROM processed_events") == 0


async def test_a_handler_that_fails_records_nothing_so_the_event_is_handled_next_time(db_pool, tenant_a):
    calls = []

    async def handler(event, tx):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("consumer bug")

    consumer = IdempotentConsumer("c", handler, pool=db_pool)
    ev = make_event(tenant_a)
    with pytest.raises(RuntimeError):
        await consumer(ev, None)
    await consumer(ev, None)
    await consumer(ev, None)
    assert len(calls) == 2  # failed once, succeeded once, then deduped


async def test_the_lru_alone_dedupes_in_one_process_and_stays_bounded():
    seen = []

    async def handler(event, tx):
        seen.append(event.id)

    consumer = IdempotentConsumer("c", handler, lru_size=2)
    events = [CloudEvent(type=TYPE, source="/t", subject=None, tenantid="t", data={}) for _ in range(3)]
    for ev in events:
        await consumer(ev, None)
        await consumer(ev, None)
    assert seen == [e.id for e in events]
    await consumer(events[0], None)  # evicted by the bound: handled again (the table is what makes it durable)
    assert seen[-1] == events[0].id


async def test_outbox_rls_hides_other_tenants_and_the_app_cannot_delete(db_pool, tenant_a, tenant_b):
    await OutboxEventBus(db_pool).publish(make_event(tenant_a))
    assert await outbox_rows(db_pool, tenant_b) == []
    async with tenant_connection(db_pool, UUID(tenant_b.id)) as conn:
        assert await conn.execute("UPDATE outbox SET attempts = 99") == "UPDATE 0"
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        with pytest.raises(Exception, match="permission denied"):
            await conn.execute("DELETE FROM outbox")


async def test_an_event_that_keeps_failing_is_left_after_max_attempts(db_pool, tenant_a):
    await OutboxEventBus(db_pool).publish(make_event(tenant_a))

    class Down:
        def subscribe(self, type, handler):
            pass

        async def publish(self, event, *, tx=None):
            raise ConnectionError("down")

    relay = OutboxRelay(db_pool, Down(), max_attempts=2)
    await relay.run_once()
    await relay.run_once()
    [row] = await outbox_rows(db_pool, tenant_a)
    assert row["attempts"] == 2 and row["published_at"] is None
    good = FakeEventBus()
    assert await OutboxRelay(db_pool, good, max_attempts=2).run_once() == 0  # given up: needs an operator, not a loop

"""Sprint 010 A2 and A3: the Kafka adapter's consumer side and the relay's side on real Postgres. By default the broker is
the in-memory fake (`tests/fake_kafka.py`). `scripts/verify/kafka.sh` runs these same tests on a live broker
(KAFKA_LIVE_BOOTSTRAP). `BACKEND` says which one ran; it is in the test ids below through the `backend` fixture."""
import asyncio
import json
import logging
import random
from collections import Counter, defaultdict
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from adapters.kafka_event_bus import dlq_topic, topic_for
from adapters.pg_outbox_events import OutboxEventBus, OutboxRelay
from core.database.tenant import tenant_connection
from ports import CloudEvent
from tests.fakes import FakeEventBus
from tests.kafka_helpers import BACKEND, make_bus, pump, read_all, unique_type

pytestmark = pytest.mark.asyncio


@pytest.fixture(params=[BACKEND])
def backend(request):
    return request.param


def make_event(etype, tenant, **data):
    return CloudEvent(type=etype, source="/test", subject="s", tenantid=str(tenant), data=data or {"k": "v"})


class Crash(BaseException):
    """A process kill: it is not an Exception, so nothing in the relay catches it."""


@pytest_asyncio.fixture
async def buses():
    made = []

    def make(**kw):
        bus, broker = make_bus(**kw)
        made.append(bus)
        return bus, broker

    yield make
    for bus in made:
        await bus.close()


async def test_publish_writes_one_record_per_event_keyed_by_tenant_in_binary_mode(backend, buses):
    bus, broker = buses()
    etype, tenant = unique_type(), uuid4()
    ev = make_event(etype, tenant, n=1)
    await bus.publish(ev)
    (rec,) = await read_all(topic_for(etype), broker, 1)
    assert rec.key == str(tenant).encode() and json.loads(rec.value) == {"n": 1}
    headers = dict(rec.headers)
    assert headers["ce_id"] == ev.id.encode() and headers["ce_type"] == etype.encode() and headers["ce_specversion"] == b"1.0"
    assert headers["ce_tenantid"] == str(tenant).encode()


async def test_a_consumer_gets_the_event_and_the_offset_is_committed_after_the_handler(backend, buses):
    bus, broker = buses()
    etype, seen = unique_type(), []

    async def handler(ev, tx):
        seen.append(ev)
        if broker is not None:  # not committed while the handler runs
            assert not broker.committed

    bus.consume(etype, handler, name="t")
    ev = make_event(etype, uuid4())
    await bus.publish(ev)
    await pump(bus, lambda: bool(seen))
    assert seen == [ev]
    if broker is not None:
        assert sum(broker.committed.values()) == 1


async def test_a_handler_that_fails_is_tried_again_and_nothing_goes_to_the_dead_letter_topic(backend, buses):
    bus, broker = buses(max_attempts=3)
    etype, calls = unique_type(), []

    async def flaky(ev, tx):
        calls.append(ev.id)
        if len(calls) < 3:
            raise RuntimeError("not yet")

    bus.consume(etype, flaky, name="t")
    await bus.publish(make_event(etype, uuid4()))
    await pump(bus, lambda: len(calls) >= 3)
    await bus.poll_once(0.2)
    assert len(calls) == 3
    if broker is not None:
        assert broker.records(dlq_topic(topic_for(etype))) == [] and sum(broker.committed.values()) == 1


async def test_a_poison_message_goes_to_the_dead_letter_topic_after_max_attempts_and_the_next_one_still_runs(backend, buses):
    bus, broker = buses(max_attempts=3)
    etype, calls, good = unique_type(), Counter(), []
    tenant = uuid4()  # one tenant, so one partition: the good event sits behind the poison one

    async def handler(ev, tx):
        calls[ev.data["n"]] += 1
        if ev.data["n"] == 1:
            raise ValueError("cannot handle this")
        good.append(ev.data["n"])

    bus.consume(etype, handler, name="t")
    poison, after = make_event(etype, tenant, n=1), make_event(etype, tenant, n=2)
    await bus.publish(poison)
    await bus.publish(after)
    await pump(bus, lambda: good == [2])
    assert calls[1] == 3 and calls[2] == 1
    (dead,) = await read_all(dlq_topic(topic_for(etype)), broker, 1)
    headers = dict(dead.headers)
    assert headers["ce_id"] == poison.id.encode() and headers["x-attempts"] == b"3"
    assert b"ValueError" in headers["x-error"] and headers["x-original-topic"] == topic_for(etype).encode()
    assert dead.key == str(tenant).encode() and json.loads(dead.value) == {"n": 1}
    if broker is not None:
        assert sum(broker.committed.values()) == 2  # the poison record was committed, so it is not delivered again


async def test_a_record_that_is_not_a_cloud_event_goes_to_the_dead_letter_topic_at_once(backend, buses):
    bus, broker = buses()
    etype, seen = unique_type(), []

    async def handler(ev, tx):
        seen.append(ev)

    bus.consume(etype, handler, name="t")
    await bus._ensure_producer()
    await bus._producer.send(topic_for(etype), key=b"k", value=b"not json at all", headers=(("ce_id", b"x"),))
    await bus.publish(make_event(etype, uuid4()))
    await pump(bus, lambda: len(seen) == 1)
    for _ in range(10):  # the bad record may sit on another partition than the good one
        await bus.poll_once(0.1)
    (dead,) = await read_all(dlq_topic(topic_for(etype)), broker, 1)
    assert dead.value == b"not json at all" and dict(dead.headers)["x-attempts"] == b"1" and dict(dead.headers)["x-error-code"] == b"decode_failed"


async def test_a_record_read_and_not_committed_is_delivered_again_and_handled_once_after_dedupe(backend, buses, db_pool, tenant_a):
    etype, name = unique_type(), "dedupe"
    group = f"g-{uuid4().hex[:8]}"
    first, broker = buses(group=group, pool=db_pool)
    handled = []

    async def handler(ev, tx):
        handled.append(ev.id)

    first.consume(etype, handler, name=name)
    ev = make_event(etype, UUID(tenant_a.id))
    await first.publish(ev)
    await pump(first, lambda: handled == [ev.id])
    await first.close()
    if broker is not None:
        broker.committed.clear()  # a crash after the handler and before the commit: the group offset is still at the start
    else:
        group = f"g-{uuid4().hex[:8]}"  # live: a new group reads the topic from the start, which is the same replay
    second, _ = buses(group=group, pool=db_pool, broker=broker)
    second.consume(etype, handler, name=name)
    for _ in range(8):
        await second.poll_once(0.2)
    if broker is not None:
        assert second._consumer.delivered == 1  # the record came again
    assert handled == [ev.id]  # delivered twice, handled once
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        assert await conn.fetchval("SELECT count(*) FROM processed_events WHERE event_id = $1", ev.id) == 1


async def test_1000_events_over_3_tenants_keep_each_tenants_order(backend, buses):
    bus, broker = buses()
    etype = unique_type()
    tenants = [uuid4() for _ in range(3)]
    rng = random.Random(10)
    order = [rng.choice(tenants) for _ in range(1000)]
    got = defaultdict(list)

    async def handler(ev, tx):
        got[ev.tenantid].append(ev.data["n"])

    bus.consume(etype, handler, name="order")
    next_n = Counter()
    for tenant in order:
        await bus.publish(make_event(etype, tenant, n=next_n[tenant]))
        next_n[tenant] += 1
    await pump(bus, lambda: sum(len(v) for v in got.values()) == 1000, timeout=120)
    assert {t: len(got[str(t)]) for t in tenants} == dict((t, next_n[t]) for t in tenants)
    for tenant in tenants:
        assert got[str(tenant)] == list(range(next_n[tenant]))  # in publish order, none lost, none repeated
    if broker is not None:  # the key is the tenant: each tenant sits on exactly one partition
        for tenant in tenants:
            parts = {r.partition for r in broker.records(topic_for(etype)) if r.key == str(tenant).encode()}
            assert len(parts) == 1


async def outbox_events(db_pool, tenants, etype, n):
    outbox = OutboxEventBus(db_pool)
    events = [make_event(etype, UUID(tenants[i % len(tenants)].id), n=i) for i in range(n)]
    for ev in events:
        await outbox.publish(ev)
    return events


class CrashingTarget:
    """Forwards to the bus, and dies after the `after`-th event is acknowledged by Kafka and before the relay marks it."""

    def __init__(self, bus, after):
        self._bus, self._after, self.sent = bus, after, 0

    async def publish(self, event, *, tx=None):
        await self._bus.publish(event, tx=tx)
        self.sent += 1
        if self.sent == self._after:
            raise Crash

    def subscribe(self, type, handler):
        raise NotImplementedError


async def test_a_relay_killed_mid_batch_loses_nothing_and_each_event_is_handled_once(backend, buses, db_pool, tenant_a, tenant_b):
    etype = unique_type()
    events = await outbox_events(db_pool, (tenant_a, tenant_b), etype, 24)
    producer, broker = buses()
    with pytest.raises(Crash):
        await OutboxRelay(db_pool, CrashingTarget(producer, after=9), batch_size=24).run_once()
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        unsent = await conn.fetchval("SELECT count(*) FROM outbox WHERE published_at IS NULL")
    assert unsent > 0  # the batch really stopped halfway
    assert await OutboxRelay(db_pool, producer, batch_size=24).run_once() > 0  # a new relay finishes the rest
    assert await OutboxRelay(db_pool, producer, batch_size=24).run_once() == 0

    consumer, _ = buses(pool=db_pool, broker=broker)
    handled = Counter()

    async def handler(ev, tx):
        handled[ev.id] += 1

    consumer.consume(etype, handler, name="after-restart")
    records = await read_all(topic_for(etype), broker, 25)
    assert len(records) >= 24  # 24 once, and the event the first relay sent without marking, a second time
    await pump(consumer, lambda: len(handled) == 24, timeout=60)
    for _ in range(5):
        await consumer.poll_once(0.3)
    assert set(handled) == {e.id for e in events} and set(handled.values()) == {1}
    if broker is not None:
        assert len(records) == 25 and Counter(dict(r.headers)["ce_id"] for r in records).most_common(1)[0][1] == 2


async def test_a_failed_send_leaves_the_row_in_the_outbox_and_the_next_pass_sends_it(backend, buses, db_pool, tenant_a):
    etype = unique_type()
    (ev,) = await outbox_events(db_pool, (tenant_a,), etype, 1)
    bus, broker = buses()
    real_send, down = bus._producer.send, {"n": 1}

    async def flaky(topic, **kw):
        if down["n"] > 0:
            down["n"] -= 1
            raise ConnectionError("broker not reachable")
        await real_send(topic, **kw)

    bus._producer.send = flaky
    relay = OutboxRelay(db_pool, bus)
    assert await relay.run_once() == 0
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        row = await conn.fetchrow("SELECT published_at, attempts FROM outbox WHERE event_id = $1", ev.id)
    assert row["published_at"] is None and row["attempts"] == 1
    assert await relay.run_once() == 1
    assert len(await read_all(topic_for(etype), broker, 1)) == 1


async def test_the_relay_closes_the_producer(backend, buses, db_pool):
    bus, _ = buses()
    await bus._ensure_producer()
    await OutboxRelay(db_pool, bus).aclose()
    assert bus._producer_started is False
    await OutboxRelay(db_pool, FakeEventBus()).aclose()  # a target with nothing to close


async def poll_through_failures(bus, done, timeout=30.0):
    """Poll until `done()`; a failed pass (the broker refused something) is just tried again, as `run` does."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not done():
        assert asyncio.get_running_loop().time() < deadline, "the consumer did not get there"
        try:
            await bus.poll_once(0.2)
        except Exception:
            pass


async def test_a_failed_dead_letter_send_does_not_lose_the_poison_record(backend, buses):
    """H1: the dead-letter send fails once. The next record's commit must not cover the poison one."""
    bus, broker = buses(max_attempts=2)
    etype, good = unique_type(), []
    tenant = uuid4()

    async def handler(ev, tx):
        if ev.data["n"] == 1:
            raise ValueError("poison")
        good.append(ev.data["n"])

    bus.consume(etype, handler, name="t")
    await bus.publish(make_event(etype, tenant, n=1))
    await bus.publish(make_event(etype, tenant, n=2))
    real_send, down = bus._producer.send, {"n": 1}

    async def flaky(topic, **kw):
        if topic.endswith(".dlq") and down["n"] > 0:
            down["n"] -= 1
            raise ConnectionError("broker not reachable")
        await real_send(topic, **kw)

    bus._producer.send = flaky
    await poll_through_failures(bus, lambda: good == [2] and down["n"] == 0)
    for _ in range(3):
        await poll_through_failures(bus, lambda: True)
        await bus.poll_once(0.1)
    (dead,) = await read_all(dlq_topic(topic_for(etype)), broker, 1)
    assert json.loads(dead.value) == {"n": 1}


async def test_a_failed_commit_replays_the_record_and_the_handler_runs_once(backend, buses):
    """H1: a commit that fails leaves the record to be read again, not skipped."""
    bus, broker = buses()
    etype, calls = unique_type(), []

    async def handler(ev, tx):
        calls.append(ev.data["n"])

    bus.consume(etype, handler, name="t")
    tenant = uuid4()
    await bus.publish(make_event(etype, tenant, n=1))
    await bus.publish(make_event(etype, tenant, n=2))
    consumer = await bus._ensure_consumer()
    real_commit, down = consumer.commit, {"n": 1}

    async def flaky_commit(record):
        if down["n"] > 0:
            down["n"] -= 1
            raise ConnectionError("commit failed")
        await real_commit(record)

    consumer.commit = flaky_commit
    await poll_through_failures(bus, lambda: calls == [1, 2])
    for _ in range(3):
        await bus.poll_once(0.1)
    assert calls == [1, 2]  # in order, none skipped, the replayed one deduped
    if broker is not None:
        assert sum(broker.committed.values()) == 2


async def test_the_error_header_and_the_log_carry_the_class_and_never_the_message(backend, buses, caplog):
    """M1: an exception message can hold a secret or input text."""
    bus, broker = buses(max_attempts=2)
    etype = unique_type()

    async def handler(ev, tx):
        raise RuntimeError("password=hunter2 input text")

    bus.consume(etype, handler, name="t")
    await bus.publish(make_event(etype, uuid4()))
    with caplog.at_level(logging.DEBUG):
        await pump_dead(bus, etype, broker)
    (dead,) = await read_all(dlq_topic(topic_for(etype)), broker, 1)
    headers = dict(dead.headers)
    assert headers["x-error"] == b"RuntimeError" and headers["x-error-code"] == b"handler_failed"
    assert b"hunter2" not in b"".join(v for _, v in dead.headers)
    assert "hunter2" not in caplog.text and "RuntimeError" in caplog.text


async def pump_dead(bus, etype, broker):
    for _ in range(10):
        await bus.poll_once(0.2)
        if broker is not None and broker.records(dlq_topic(topic_for(etype))):
            return


class Recorder:
    """A relay target that fails for chosen events the first time it sees them."""

    def __init__(self, fail_once=()):
        self.fail_once, self.sent = set(fail_once), []

    async def publish(self, event, *, tx=None):
        if event.data["n"] in self.fail_once:
            self.fail_once.discard(event.data["n"])
            raise ConnectionError("broker not reachable")
        self.sent.append((event.tenantid, event.data["n"]))


async def test_the_relay_does_not_send_a_later_row_of_a_tenant_past_a_failed_one(db_pool, tenant_a, tenant_b):
    """M2: event 1 of tenant A fails once. Event 2 of tenant A must wait. Tenant B is not held up."""
    outbox = OutboxEventBus(db_pool)
    a1, a2 = make_event("platform.test.m2.v1", UUID(tenant_a.id), n=1), make_event("platform.test.m2.v1", UUID(tenant_a.id), n=2)
    b1 = make_event("platform.test.m2.v1", UUID(tenant_b.id), n=10)
    for ev in (a1, b1, a2):
        await outbox.publish(ev)
    target = Recorder(fail_once={1})
    relay = OutboxRelay(db_pool, target)
    assert await relay.run_once() == 1
    assert target.sent == [(tenant_b.id, 10)]  # A's second event did not overtake the failed first one
    assert await relay.run_once() == 2
    assert [n for t, n in target.sent if t == tenant_a.id] == [1, 2]


async def test_a_send_that_was_applied_but_not_acknowledged_is_sent_again_and_handled_once(backend, buses, db_pool, tenant_a):
    """M3: the record is in Kafka, the client heard nothing. The retry is a duplicate that dedupe absorbs."""
    etype = unique_type()
    (ev,) = await outbox_events(db_pool, (tenant_a,), etype, 1)
    bus, broker = buses(pool=db_pool)
    if broker is not None:
        broker.lost_acks = 1
    else:
        real_send, lost = bus._producer.send, {"n": 1}

        async def apply_then_fail(topic, **kw):
            await real_send(topic, **kw)
            if lost["n"] > 0:
                lost["n"] -= 1
                raise TimeoutError("acknowledgement lost")

        bus._producer.send = apply_then_fail
    relay = OutboxRelay(db_pool, bus)
    assert await relay.run_once() == 0  # the relay saw a failure and kept the row
    assert await relay.run_once() == 1
    handled = Counter()

    async def handler(e, tx):
        handled[e.id] += 1

    bus.consume(etype, handler, name="m3")
    records = await read_all(topic_for(etype), broker, 2)
    assert len(records) == 2  # the duplicate is really in the topic
    await pump(bus, lambda: handled[ev.id] >= 1)
    for _ in range(4):
        await bus.poll_once(0.2)
    assert handled == {ev.id: 1}


async def test_a_send_that_never_returns_fails_within_the_send_timeout(backend, buses):
    """L2: the relay holds a row lock while it waits, so the wait is bounded."""
    bus, _ = buses()
    bus._producer_started = True  # skip the start: this producer only hangs

    async def hang(topic, **kw):
        await asyncio.sleep(30)

    bus._producer.send = hang
    bus._config = type(bus._config)(**{**bus._config.__dict__, "send_timeout_seconds": 0.1})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bus.publish(make_event(unique_type(), uuid4())), 5)

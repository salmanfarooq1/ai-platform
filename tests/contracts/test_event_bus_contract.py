"""One contract for every `EventBus` adapter: in-process, a recording fake and the Postgres outbox (Sprint 007).
The Kafka adapter (010) must pass it too."""
from datetime import timezone
from uuid import uuid4

import asyncpg
import psycopg2
import pytest
import pytest_asyncio

from adapters.inprocess_events import InProcessEventBus
from adapters.pg_outbox_events import OutboxEventBus
from ports import CloudEvent
from tests.fakes import FakeEventBus

TENANT = str(uuid4())  # a real uuid: the outbox keys its rows by tenant


@pytest_asyncio.fixture(params=["in-process", "fake-recording", "outbox"])
async def bus(request):
    if request.param != "outbox":
        yield {"in-process": InProcessEventBus, "fake-recording": FakeEventBus}[request.param]()
        return
    owner_dsn = request.getfixturevalue("database_url")
    request.getfixturevalue("clean_state")
    conn = psycopg2.connect(owner_dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("INSERT INTO tenants (id, slug, name) VALUES (%s, %s, %s)", (TENANT, f"contract-{TENANT[:8]}", "Contract"))
    conn.close()
    pool = await asyncpg.create_pool(dsn=request.getfixturevalue("app_database_url"), min_size=1, max_size=3, statement_cache_size=0)
    try:
        yield OutboxEventBus(pool)
    finally:
        await pool.close()


def event(type="platform.test.thing.v1", **data):
    return CloudEvent(type=type, source="/test", subject="s-1", tenantid=TENANT, data=data or {"k": "v"})


async def test_a_subscriber_gets_the_events_of_its_type_only(bus):
    seen = []

    async def handler(ev, tx):
        seen.append(ev)

    bus.subscribe("platform.test.thing.v1", handler)
    wanted, other = event(), event(type="platform.test.other.v1")
    await bus.publish(other)
    await bus.publish(wanted)
    assert seen == [wanted]


async def test_handlers_run_in_subscription_order_and_a_wildcard_gets_everything(bus):
    order = []

    async def first(ev, tx):
        order.append(("first", ev.type))

    async def second(ev, tx):
        order.append(("second", ev.type))

    async def everything(ev, tx):
        order.append(("all", ev.type))

    bus.subscribe("platform.test.thing.v1", first)
    bus.subscribe("platform.test.thing.v1", second)
    bus.subscribe("*", everything)
    await bus.publish(event())
    await bus.publish(event(type="platform.test.other.v1"))
    assert order == [("first", "platform.test.thing.v1"), ("second", "platform.test.thing.v1"),
                     ("all", "platform.test.thing.v1"), ("all", "platform.test.other.v1")]


async def test_the_callers_transaction_context_reaches_the_handler(bus):
    got = []

    async def handler(ev, tx):
        got.append(tx)

    bus.subscribe("platform.test.thing.v1", handler)
    sentinel = object()
    await bus.publish(event(), tx=sentinel)
    await bus.publish(event())
    assert got == [sentinel, None]


async def test_a_failing_handler_does_not_stop_the_others_or_fail_the_publisher(bus):
    seen = []

    async def boom(ev, tx):
        raise RuntimeError("subscriber bug")

    async def fine(ev, tx):
        seen.append(ev.id)

    bus.subscribe("platform.test.thing.v1", boom)
    bus.subscribe("platform.test.thing.v1", fine)
    ev = event()
    await bus.publish(ev)
    assert seen == [ev.id]


async def test_publishing_with_no_subscriber_is_fine(bus):
    await bus.publish(event())


def test_a_cloud_event_is_a_valid_cloudevents_1_0_envelope():
    ev = event(decision_id="d-1")
    body = ev.to_dict()
    assert body["specversion"] == "1.0"
    assert {"id", "source", "type", "time", "subject", "tenantid", "data", "datacontenttype"} <= set(body)
    assert body["tenantid"] == TENANT and body["data"] == {"decision_id": "d-1"}
    assert ev.time.tzinfo is not None and ev.time.utcoffset() == timezone.utc.utcoffset(None)
    assert event().id != event().id  # a fresh id per event


@pytest.mark.parametrize("override", [{"specversion": "0.3"}, {"id": ""}, {"source": ""}, {"type": ""}, {"tenantid": ""}])
def test_an_invalid_cloud_event_is_refused(override):
    fields = {"type": "t", "source": "/s", "subject": None, "tenantid": "x", "data": {}, **override}
    with pytest.raises(ValueError):
        CloudEvent(**fields)


async def test_the_bus_only_publishes_cloud_events():
    with pytest.raises(TypeError):
        await InProcessEventBus().publish({"type": "not an event"})

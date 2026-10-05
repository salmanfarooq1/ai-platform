"""How the Kafka tests get a bus (Sprint 010). By default the broker is the in-memory fake in `tests/fake_kafka.py`.
With KAFKA_LIVE_BOOTSTRAP set (by `scripts/verify/kafka.sh`) the same tests run against a real broker through aiokafka.
`BACKEND` is part of every test id, so a report shows which one ran."""
import asyncio
import os
from collections.abc import Callable
from uuid import uuid4

from adapters.kafka_event_bus import AioKafkaConsumer, KafkaConfig, KafkaEventBus, KafkaRecord
from core.database.tenant import DbPool
from tests.fake_kafka import FakeKafkaBroker, FakeKafkaConsumer, FakeKafkaProducer

LIVE_BOOTSTRAP = os.environ.get("KAFKA_LIVE_BOOTSTRAP", "").strip()
BACKEND = "kafka-live" if LIVE_BOOTSTRAP else "kafka-fake"


def unique_type(area: str = "test") -> str:
    """A fresh event type, so a live run never meets records another test left in the topic."""
    return f"platform.{area}.t{uuid4().hex[:10]}.v1"


def make_bus(
    *, pool: DbPool | None = None, broker: FakeKafkaBroker | None = None, group: str | None = None,
    max_attempts: int = 3, backoff: float = 0.0, send_timeout: float = 15.0,
) -> tuple[KafkaEventBus, FakeKafkaBroker | None]:
    """A bus on the fake `broker` (made if none is given), or on the live broker. Two buses on one fake broker and one
    group id model a restart of a consumer."""
    config = KafkaConfig(
        bootstrap=LIVE_BOOTSTRAP or "fake:9092", client_id="gap-test", group_id=group or f"g-{uuid4().hex[:10]}",
        max_attempts=max_attempts, retry_backoff_seconds=backoff, send_timeout_seconds=send_timeout,
    )
    if LIVE_BOOTSTRAP:
        return KafkaEventBus(config, pool=pool), None
    broker = broker or FakeKafkaBroker()
    return KafkaEventBus(
        config, pool=pool, producer=FakeKafkaProducer(broker),
        consumer_factory=lambda topics: FakeKafkaConsumer(broker, config.group_id, topics),
    ), broker


async def read_all(topic: str, broker: FakeKafkaBroker | None, expected: int, timeout: float = 30.0) -> list[KafkaRecord]:
    """The records of `topic` (from the fake broker, or read live by a throwaway group), waiting for `expected` of them."""
    if broker is not None:
        return broker.records(topic)
    consumer = AioKafkaConsumer(KafkaConfig(bootstrap=LIVE_BOOTSTRAP, group_id=f"read-{uuid4().hex[:10]}"), [topic])
    await consumer.start()
    out: list[KafkaRecord] = []
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while len(out) < expected and asyncio.get_running_loop().time() < deadline:
            rec = await consumer.next(1.0)
            if rec is not None:
                out.append(rec)
    finally:
        await consumer.stop()
    return out


async def pump(bus: KafkaEventBus, done: Callable[[], bool], timeout: float = 60.0) -> None:
    """Poll the bus until `done()`, or fail after `timeout` seconds."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not done():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("the consumer did not reach the expected state in time")
        await bus.poll_once(0.2)

"""The Kafka adapter behind the EventBus port (ADR-0008, Sprint 010). The only module that imports `aiokafka`.

Publishing. `KafkaEventBus.publish` sends the event to the topic of its type and waits for the broker to acknowledge it
(`acks=all`, idempotent producer). The topic is `platform.<type without its version>`, so `platform.gateway.decision.v1`
goes to `platform.gateway.decision`. The key is the tenant id, so one tenant's events stay in order inside a partition.
The event is a CloudEvent in binary content mode: the attributes are `ce_*` headers, `content-type` is the data content
type and the value is the JSON `data`.

Nothing in a request reaches Kafka. With `EVENT_BUS=kafka` the API still writes the outbox in the decision's
transaction, and only the outbox relay (`OutboxRelay`) publishes to this bus, so a decision row is never lost because
of the bus. `subscribe` keeps the port's meaning: handlers run in the publisher's task right after the send.

Consuming. `consume(type, handler, name=...)` registers a consumer-group handler. `poll_once` (and `run`, which loops it)
reads one record, decodes it and runs the handlers wrapped in `IdempotentConsumer`, so a record seen twice (the relay
sends at least once) is handled once per CloudEvent id. The offset is committed only after every handler succeeded.
A handler that raises is tried again, up to `max_attempts`. Then the record goes to `<topic>.dlq` with error headers
and its offset is committed, so one poison message does not block the partition. A record that cannot be decoded goes
to the dead-letter topic at once.

The wire client sits behind the small `KafkaProducer` and `KafkaConsumer` protocols below. `AioKafka*` are the real ones.
Tests use the in-memory broker in `tests/fake_kafka.py`.
"""
import asyncio
import json
import logging
import re
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition  # type: ignore[import-untyped,unused-ignore]
from pydantic import SecretStr

from adapters.inprocess_events import InProcessEventBus
from adapters.pg_outbox_events import IdempotentConsumer
from core.database.tenant import DbPool
from ports.events import (
    DECISION_RECORDED,
    DECISIONS_PURGED,
    INGEST_COMPLETED,
    SPEC_VERSION,
    WILDCARD,
    CloudEvent,
    Handler,
)

logger = logging.getLogger("adapters.kafka")

TOPIC_PREFIX = "platform"
DLQ_SUFFIX = ".dlq"
KNOWN_TYPES = (DECISION_RECORDED, INGEST_COMPLETED, DECISIONS_PURGED)
_VERSION_SUFFIX = re.compile(r"\.v\d+$")

Headers = tuple[tuple[str, bytes], ...]


def topic_for(event_type: str) -> str:
    """`platform.gateway.decision.v1` -> `platform.gateway.decision`. A type outside `platform.` is placed under it."""
    base = _VERSION_SUFFIX.sub("", event_type)
    return base if base.startswith(TOPIC_PREFIX + ".") else f"{TOPIC_PREFIX}.{base}"


def dlq_topic(topic: str) -> str:
    return topic + DLQ_SUFFIX


@dataclass(frozen=True)
class KafkaRecord:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes | None
    headers: Headers


class KafkaProducer(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, topic: str, *, key: bytes | None, value: bytes | None, headers: Headers) -> None:
        """Send one record and return when the broker acknowledged it. Raises when it did not."""
        ...


class KafkaConsumer(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def next(self, timeout: float) -> KafkaRecord | None:
        """The next record of the group, or None after `timeout` seconds without one."""
        ...

    async def commit(self, record: KafkaRecord) -> None:
        """Commit the group's offset past `record`. Records of that partition before it are done too."""
        ...

    async def seek(self, record: KafkaRecord) -> None:
        """Move the read position of `record`'s partition back to `record`, so the next `next` returns it again."""
        ...


ConsumerFactory = Callable[[Sequence[str]], KafkaConsumer]


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap: str
    client_id: str = "gap-platform"
    group_id: str = "gap-platform"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: SecretStr | None = None  # a SecretStr: its repr is masked, so a log line cannot show it
    max_attempts: int = 5
    retry_backoff_seconds: float = 0.5
    request_timeout_seconds: float = 10.0  # one request to the broker
    send_timeout_seconds: float = 15.0  # a whole send, acknowledgement included: the relay holds a row lock meanwhile

    def client_options(self) -> dict[str, Any]:
        """The options both aiokafka clients share. The only place the SASL password is unwrapped."""
        options: dict[str, Any] = {
            "bootstrap_servers": [part.strip() for part in self.bootstrap.split(",") if part.strip()],
            "client_id": self.client_id,
            "security_protocol": self.security_protocol,
            "request_timeout_ms": max(1, int(self.request_timeout_seconds * 1000)),
        }
        if self.security_protocol in ("SSL", "SASL_SSL"):
            options["ssl_context"] = ssl.create_default_context()
        if self.security_protocol.startswith("SASL"):
            options["sasl_mechanism"] = self.sasl_mechanism
            options["sasl_plain_username"] = self.sasl_username
            options["sasl_plain_password"] = self.sasl_password.get_secret_value() if self.sasl_password else None
        return options


class AioKafkaProducer:
    """`acks=all` with an idempotent producer: a retry inside the client does not duplicate or reorder a record."""

    def __init__(self, config: KafkaConfig) -> None:
        self._config = config
        self._client: Any = None  # aiokafka clients need a running loop, so `start` makes it

    async def start(self) -> None:
        self._client = AIOKafkaProducer(acks="all", enable_idempotence=True, **self._config.client_options())
        await self._client.start()

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.stop()

    async def send(self, topic: str, *, key: bytes | None, value: bytes | None, headers: Headers) -> None:
        await self._client.send_and_wait(topic, value=value, key=key, headers=list(headers))


class AioKafkaConsumer:
    """A consumer-group member that never auto-commits: the adapter commits after the handlers succeed."""

    def __init__(self, config: KafkaConfig, topics: Sequence[str]) -> None:
        self._config, self._topics = config, list(topics)
        self._client: Any = None

    async def start(self) -> None:
        self._client = AIOKafkaConsumer(
            *self._topics, group_id=self._config.group_id, enable_auto_commit=False, auto_offset_reset="earliest",
            **self._config.client_options(),
        )
        await self._client.start()

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.stop()

    async def next(self, timeout: float) -> KafkaRecord | None:
        batches = await self._client.getmany(timeout_ms=max(1, int(timeout * 1000)), max_records=1)
        for records in batches.values():
            for rec in records:
                headers = tuple((str(k), bytes(v) if v is not None else b"") for k, v in (rec.headers or ()))
                return KafkaRecord(rec.topic, rec.partition, rec.offset, rec.key, rec.value, headers)
        return None

    async def seek(self, record: KafkaRecord) -> None:
        self._client.seek(TopicPartition(record.topic, record.partition), record.offset)

    async def commit(self, record: KafkaRecord) -> None:
        await self._client.commit({TopicPartition(record.topic, record.partition): record.offset + 1})


# --------------------------------------------------------------------------------- CloudEvents binary content mode

def encode_event(event: CloudEvent) -> tuple[bytes, Headers]:
    """The record value and headers of an event (CloudEvents Kafka binding, binary mode)."""
    headers: list[tuple[str, bytes]] = [
        ("ce_specversion", event.specversion.encode()), ("ce_id", event.id.encode()), ("ce_source", event.source.encode()),
        ("ce_type", event.type.encode()), ("ce_time", event.time.isoformat().encode()),
        ("ce_tenantid", event.tenantid.encode()), ("content-type", event.datacontenttype.encode()),
    ]
    if event.subject is not None:
        headers.append(("ce_subject", event.subject.encode()))
    return json.dumps(event.data, separators=(",", ":"), sort_keys=True).encode(), tuple(headers)


def decode_event(value: bytes | None, headers: Headers) -> CloudEvent:
    """The inverse of `encode_event`. Raises ValueError for a record that is not a CloudEvent in binary mode."""
    attrs = {name: raw.decode() for name, raw in headers}
    missing = [name for name in ("ce_specversion", "ce_id", "ce_source", "ce_type", "ce_time", "ce_tenantid") if not attrs.get(name)]
    if missing:
        raise ValueError(f"not a CloudEvent: missing header(s) {', '.join(missing)}")
    if attrs["ce_specversion"] != SPEC_VERSION:
        raise ValueError(f"unsupported CloudEvents specversion {attrs['ce_specversion']!r}")
    data = json.loads(value) if value else {}
    if not isinstance(data, dict):
        raise ValueError("the event data is not a JSON object")
    return CloudEvent(
        type=attrs["ce_type"], source=attrs["ce_source"], subject=attrs.get("ce_subject"), tenantid=attrs["ce_tenantid"],
        data=data, id=attrs["ce_id"], time=datetime.fromisoformat(attrs["ce_time"]),
        datacontenttype=attrs.get("content-type", "application/json"),
    )


def _error_class(exc: BaseException) -> bytes:
    """Only the exception class. Its message may hold input text or a secret, so it goes nowhere (M1)."""
    return type(exc).__name__.encode()


# ------------------------------------------------------------------------------------------------------ the adapter

class KafkaEventBus:
    """An `EventBus` that publishes to Kafka and can consume from it as one consumer group (`config.group_id`)."""

    def __init__(
        self, config: KafkaConfig, *, pool: DbPool | None = None, producer: KafkaProducer | None = None,
        consumer_factory: ConsumerFactory | None = None,
    ) -> None:
        self._config = config
        self._pool = pool
        self._producer: KafkaProducer = producer or AioKafkaProducer(config)
        self._consumer_factory: ConsumerFactory = consumer_factory or (lambda topics: AioKafkaConsumer(config, topics))
        self._producer_started = False
        self._producer_lock = asyncio.Lock()
        self._local = InProcessEventBus()
        self._consumers: dict[str, list[Handler]] = {}
        self._consumer: KafkaConsumer | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # -- publishing -------------------------------------------------------------------------------------------
    def subscribe(self, type: str, handler: Handler) -> None:
        """In-process subscribers, as for every bus: they run in the publisher's task after the send."""
        self._local.subscribe(type, handler)

    async def _ensure_producer(self) -> None:
        async with self._producer_lock:
            if not self._producer_started:
                await self._producer.start()
                self._producer_started = True

    async def publish(self, event: CloudEvent, *, tx: Any = None) -> None:
        """Send the event and wait for the acknowledgement. A send failure raises, so the relay keeps the row."""
        if not isinstance(event, CloudEvent):
            raise TypeError("publish() takes a CloudEvent")
        await self._ensure_producer()
        value, headers = encode_event(event)
        # Sends are sequential and each waits for its acknowledgement: that is what keeps a tenant's order (ADR-0008).
        await asyncio.wait_for(
            self._producer.send(topic_for(event.type), key=event.tenantid.encode(), value=value, headers=headers),
            self._config.send_timeout_seconds,
        )
        await self._local.publish(event, tx=tx)

    # -- consuming --------------------------------------------------------------------------------------------
    def consume(self, type: str, handler: Handler, *, name: str) -> None:
        """Register a consumer-group handler for `type` (or `*`: the known platform types and any type named here).
        `name` identifies this consumer in `processed_events`. With a pool the CloudEvent id is deduped in Postgres, and
        the handler receives the deduping connection as `tx`. Without one an in-process LRU dedupes."""
        if self._consumer is not None:
            raise RuntimeError("register consumers before the first poll")
        wrapped = IdempotentConsumer(f"{name}:{type}", handler, pool=self._pool)
        self._consumers.setdefault(type, []).append(wrapped)

    def _topics(self) -> list[str]:
        types = {t for t in self._consumers if t != WILDCARD}
        if WILDCARD in self._consumers:
            types |= set(KNOWN_TYPES)
        return sorted({topic_for(t) for t in types})

    async def _ensure_consumer(self) -> KafkaConsumer:
        if self._consumer is None:
            topics = self._topics()
            if not topics:
                raise RuntimeError("no consumer is registered")
            consumer = self._consumer_factory(topics)
            await consumer.start()
            self._consumer = consumer
        return self._consumer

    async def poll_once(self, timeout: float = 1.0) -> bool:
        """Handle at most one record. Returns False when none arrived within `timeout`."""
        await self._ensure_producer()  # the dead-letter send needs it
        consumer = await self._ensure_consumer()
        record = await consumer.next(timeout)
        if record is None:
            return False
        try:
            await self._handle(consumer, record)
        except BaseException:
            # A failed dead-letter send or commit: go back to this record. Otherwise the next record's commit would
            # cover it and it would be lost (H1). Cancellation rewinds too, so a stopped loop loses nothing.
            await consumer.seek(record)
            raise
        return True

    async def _handle(self, consumer: KafkaConsumer, record: KafkaRecord) -> None:
        try:
            event = decode_event(record.value, record.headers)
        except (ValueError, UnicodeDecodeError) as exc:
            logger.error("undecodable record sent to the dead-letter topic: %s[%s]@%s", record.topic, record.partition, record.offset)
            await self._dead_letter(record, exc, attempts=1, code="decode_failed")
            await consumer.commit(record)
            return
        handlers = [*self._consumers.get(event.type, []), *self._consumers.get(WILDCARD, [])]
        last: Exception | None = None
        for attempt in range(1, self._config.max_attempts + 1):
            try:
                for handler in handlers:
                    await handler(event, None)
                await consumer.commit(record)
                return
            except Exception as exc:
                last = exc
                logger.warning(
                    "handler failed: event_id=%s attempt=%d/%d error=%s", event.id, attempt, self._config.max_attempts,
                    type(exc).__name__,
                )
                if attempt < self._config.max_attempts and self._config.retry_backoff_seconds > 0:
                    await asyncio.sleep(self._config.retry_backoff_seconds)
        assert last is not None
        logger.error("event sent to the dead-letter topic: event_id=%s topic=%s", event.id, record.topic)
        await self._dead_letter(record, last, attempts=self._config.max_attempts, code="handler_failed")
        await consumer.commit(record)

    async def _dead_letter(self, record: KafkaRecord, exc: BaseException, *, attempts: int, code: str) -> None:
        """Copy the record to `<topic>.dlq` with the error class and a code (never the message). If this send fails it
        raises. `poll_once` then seeks back to the record, so it is read again and not lost."""
        extra: Headers = (
            ("x-error", _error_class(exc)), ("x-error-code", code.encode()), ("x-attempts", str(attempts).encode()),
            ("x-original-topic", record.topic.encode()), ("x-original-partition", str(record.partition).encode()),
            ("x-original-offset", str(record.offset).encode()), ("x-group-id", self._config.group_id.encode()),
        )
        await self._producer.send(dlq_topic(record.topic), key=record.key, value=record.value, headers=(*record.headers, *extra))

    async def run(self, stop: asyncio.Event, *, poll_timeout: float = 1.0) -> None:
        """Poll until `stop` is set. A failure of the broker is logged and tried again after a pause."""
        while not stop.is_set():
            try:
                await self.poll_once(poll_timeout)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("kafka consumer pass failed", exc_info=True)
                await asyncio.sleep(max(self._config.retry_backoff_seconds, 0.1))

    def start_consuming(self) -> None:
        self._stop = asyncio.Event()
        self._consumer_task = asyncio.create_task(self.run(self._stop))

    async def close(self) -> None:
        """Stop the consumer loop, the consumer and the producer. Safe to call twice."""
        if self._consumer_task is not None:
            self._stop.set()
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)
            self._consumer_task = None
        if self._consumer is not None:
            consumer, self._consumer = self._consumer, None
            await consumer.stop()
        if self._producer_started:
            self._producer_started = False
            await self._producer.stop()


def build_kafka_bus(settings: Any, pool: DbPool | None = None) -> KafkaEventBus:
    """The bus the relay publishes to, from `Settings` (EVENT_BUS=kafka)."""
    return KafkaEventBus(
        KafkaConfig(
            bootstrap=str(settings.kafka_bootstrap), client_id=settings.kafka_client_id, group_id=settings.kafka_group_id,
            security_protocol=settings.kafka_security_protocol, sasl_mechanism=settings.kafka_sasl_mechanism,
            sasl_username=settings.kafka_sasl_username, sasl_password=settings.kafka_sasl_password,
            max_attempts=settings.kafka_max_attempts, retry_backoff_seconds=settings.kafka_retry_backoff_seconds,
            request_timeout_seconds=settings.kafka_request_timeout_seconds,
            send_timeout_seconds=settings.kafka_send_timeout_seconds,
        ),
        pool=pool,
    )


__all__ = [
    "AioKafkaConsumer", "AioKafkaProducer", "KafkaConfig", "KafkaConsumer", "KafkaEventBus", "KafkaProducer", "KafkaRecord",
    "build_kafka_bus", "decode_event", "dlq_topic", "encode_event", "topic_for",
]

"""An in-memory Kafka for the adapter tests (Sprint 010). It is a model of the broker behaviours the adapter relies on,
not a recording of a real run: the live run is `scripts/verify/kafka.sh`.

Modelled: topics made on first use with a fixed number of partitions, the partition chosen by the murmur2 hash of the key
(Kafka's default), an offset per partition, a committed offset per consumer group and partition, a consumer that starts
at the committed offset (so a record that was read and not committed is delivered again after a restart), and an
acknowledgement only after the record is appended. A send can also be applied and then raise (`lost_acks`). Not modelled: several members in one group (one consumer owns all
partitions), rebalances, replication, retention and transactions.
"""
import asyncio
from dataclasses import dataclass, field

from adapters.kafka_event_bus import Headers, KafkaRecord


def murmur2(data: bytes) -> int:
    """The murmur2 hash Kafka's default partitioner uses for a key."""
    m, r = 0x5BD1E995, 24
    h = (0x9747B28C ^ len(data)) & 0xFFFFFFFF
    for i in range(len(data) // 4):
        k = int.from_bytes(data[i * 4:i * 4 + 4], "little")
        k = (k * m) & 0xFFFFFFFF
        k ^= k >> r
        k = (k * m) & 0xFFFFFFFF
        h = ((h * m) & 0xFFFFFFFF) ^ k
    tail, off = len(data) % 4, len(data) - len(data) % 4
    if tail == 3:
        h ^= data[off + 2] << 16
    if tail >= 2:
        h ^= data[off + 1] << 8
    if tail >= 1:
        h ^= data[off]
        h = (h * m) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * m) & 0xFFFFFFFF
    h ^= h >> 15
    return h


def partition_of(key: bytes, partitions: int) -> int:
    return (murmur2(key) & 0x7FFFFFFF) % partitions


@dataclass
class FakeKafkaBroker:
    partitions: int = 3
    topics: dict[str, list[list[KafkaRecord]]] = field(default_factory=dict)
    committed: dict[tuple[str, str, int], int] = field(default_factory=dict)  # (group, topic, partition) -> next offset
    send_failures: int = 0  # the next N sends raise, to model an unreachable broker
    lost_acks: int = 0  # the next N sends are applied and then raise: the record is in the log, the client never heard
    sends: int = 0

    def __post_init__(self) -> None:
        self._appended = asyncio.Condition()

    def log(self, topic: str, partition: int) -> list[KafkaRecord]:
        return self.topics.setdefault(topic, [[] for _ in range(self.partitions)])[partition]

    def records(self, topic: str) -> list[KafkaRecord]:
        """Every record of a topic, partition by partition."""
        return [rec for part in self.topics.get(topic, []) for rec in part]

    async def append(self, topic: str, key: bytes | None, value: bytes | None, headers: Headers) -> KafkaRecord:
        self.sends += 1
        if self.send_failures > 0:
            self.send_failures -= 1
            raise ConnectionError("fake broker: not reachable")
        self.topics.setdefault(topic, [[] for _ in range(self.partitions)])
        partition = partition_of(key, self.partitions) if key is not None else self.sends % self.partitions
        log = self.log(topic, partition)
        rec = KafkaRecord(topic, partition, len(log), key, value, headers)
        log.append(rec)
        async with self._appended:
            self._appended.notify_all()
        if self.lost_acks > 0:
            self.lost_acks -= 1
            raise TimeoutError("fake broker: the acknowledgement was lost")
        return rec

    async def wait_for_append(self, timeout: float) -> None:
        async with self._appended:
            try:
                await asyncio.wait_for(self._appended.wait(), timeout)
            except asyncio.TimeoutError:
                pass


class FakeKafkaProducer:
    def __init__(self, broker: FakeKafkaBroker) -> None:
        self._broker = broker
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send(self, topic: str, *, key: bytes | None, value: bytes | None, headers: Headers) -> None:
        await self._broker.append(topic, key, value, headers)


class FakeKafkaConsumer:
    """One group member that owns every partition of its topics. It reads from the committed offset, hands out records
    in partition order, and commits only when told to."""

    def __init__(self, broker: FakeKafkaBroker, group: str, topics: list[str] | tuple[str, ...]) -> None:
        self._broker, self._group, self._topics = broker, group, list(topics)
        self._position: dict[tuple[str, int], int] = {}
        self._turn = 0
        self.started = False
        self.stopped = False
        self.delivered = 0

    async def start(self) -> None:
        self.started = True
        for topic in self._topics:
            self._broker.topics.setdefault(topic, [[] for _ in range(self._broker.partitions)])
            for p in range(self._broker.partitions):
                self._position[(topic, p)] = self._broker.committed.get((self._group, topic, p), 0)

    async def stop(self) -> None:
        self.stopped = True

    def _take(self) -> KafkaRecord | None:
        keys = sorted(self._position)
        for i in range(len(keys)):
            topic, p = keys[(self._turn + i) % len(keys)]
            log = self._broker.log(topic, p)
            pos = self._position[(topic, p)]
            if pos < len(log):
                self._position[(topic, p)] = pos + 1
                self._turn = (self._turn + i + 1) % len(keys)
                self.delivered += 1
                return log[pos]
        return None

    async def next(self, timeout: float) -> KafkaRecord | None:
        rec = self._take()
        if rec is None and timeout > 0:
            await self._broker.wait_for_append(timeout)
            rec = self._take()
        return rec

    async def seek(self, record: KafkaRecord) -> None:
        self._position[(record.topic, record.partition)] = record.offset

    async def commit(self, record: KafkaRecord) -> None:
        key = (self._group, record.topic, record.partition)
        self._broker.committed[key] = max(self._broker.committed.get(key, 0), record.offset + 1)

"""The transactional outbox behind the EventBus port, on Postgres (ADR-0008, Sprint 007).

`OutboxEventBus.publish(event, tx=conn)` writes the event to the `outbox` table on the caller's connection, so the
event commits or rolls back with the state change that produced it (a decision row, a finished job). Subscribers
of this bus run in the publisher's task right after the write, exactly as with the in-process bus, and see `tx`.
They are for work that must commit with the change. A rolled-back transaction leaves no outbox row, so nothing
leaves the system for a change that never happened.

`OutboxRelay` is the other half. It lists the rows not yet published, publishes each one to a target `EventBus`
(the in-process bus today, the Kafka adapter in Sprint 010), and marks it sent in the same transaction. The
guarantee is at least once: a crash after the target got the event and before the mark commits sends it again.
`IdempotentConsumer` is how a consumer makes that safe: it skips an event id it has already handled.
"""
import json
import logging
from collections import OrderedDict
from typing import Any
from uuid import UUID

from asyncpg import Connection

from adapters.inprocess_events import InProcessEventBus
from core.database.tenant import DbPool, tenant_connection
from ports.events import CloudEvent, EventBus, Handler

logger = logging.getLogger("adapters.outbox")

_INSERT = """
INSERT INTO outbox (tenant_id, event_id, event) VALUES ($1, $2, $3::jsonb)
ON CONFLICT (tenant_id, event_id) DO NOTHING
"""


async def write_outbox(conn: Connection, event: CloudEvent) -> None:
    """Put the event in the outbox on `conn` (a connection inside a tenant transaction). Publishing the same
    event id twice stores it once."""
    await conn.execute(_INSERT, UUID(event.tenantid), event.id, json.dumps(event.to_dict()))


class OutboxEventBus:
    """An `EventBus` whose `publish` is durable. `tx` should be the connection of the transaction that holds the
    state change. With no `tx` the event gets a transaction of its own. A write failure raises, so the publisher
    fails (the gateway turns that into a denied allow, M1)."""

    def __init__(self, pool: DbPool) -> None:
        self._pool = pool
        self._local = InProcessEventBus()

    def subscribe(self, type: str, handler: Handler) -> None:
        self._local.subscribe(type, handler)

    async def publish(self, event: CloudEvent, *, tx: Any = None) -> None:
        if not isinstance(event, CloudEvent):
            raise TypeError("publish() takes a CloudEvent")
        if isinstance(tx, Connection):
            await write_outbox(tx, event)
        else:
            async with tenant_connection(self._pool, UUID(event.tenantid)) as conn:
                await write_outbox(conn, event)
        await self._local.publish(event, tx=tx)


class OutboxRelay:
    """Publishes outbox rows to `target`, oldest first, at least once. Safe to run in several processes: a row is
    locked while it is sent, and a locked row is skipped."""

    def __init__(self, pool: DbPool, target: EventBus, *, batch_size: int = 50, max_attempts: int = 10) -> None:
        self._pool = pool
        self._target = target
        self._batch = batch_size
        self._max_attempts = max_attempts

    async def run_once(self) -> int:
        """One pass. Returns how many events were published."""
        pending = await self._pool.fetch("SELECT outbox_id, outbox_tenant FROM outbox_pending($1, $2)", self._batch, self._max_attempts)
        sent = 0
        for row in pending:
            if await self._send(row["outbox_id"], row["outbox_tenant"]):
                sent += 1
        return sent

    async def _send(self, outbox_id: UUID, tenant_id: UUID) -> bool:
        try:
            async with tenant_connection(self._pool, tenant_id) as conn:
                record = await conn.fetchrow(
                    "SELECT event FROM outbox WHERE id = $1 AND published_at IS NULL FOR UPDATE SKIP LOCKED", outbox_id,
                )
                if record is None:  # another relay has it, or it is already sent
                    return False
                body = record["event"]
                event = CloudEvent.from_dict(json.loads(body) if isinstance(body, str) else body)
                # `tx` is this transaction, so a consumer that dedupes in Postgres commits with the mark below.
                await self._target.publish(event, tx=conn)
                await conn.execute("UPDATE outbox SET published_at = NOW(), attempts = attempts + 1 WHERE id = $1", outbox_id)
            return True
        except Exception:
            logger.error("outbox event not published: outbox_id=%s", outbox_id, exc_info=True)
            try:
                async with tenant_connection(self._pool, tenant_id) as conn:
                    await conn.execute("UPDATE outbox SET attempts = attempts + 1 WHERE id = $1", outbox_id)
            except Exception:
                logger.error("outbox attempt not counted: outbox_id=%s", outbox_id, exc_info=True)
            return False


class IdempotentConsumer:
    """Wraps a handler so it runs once per CloudEvent id. A small LRU stops repeats in this process. With a pool,
    the `processed_events` table stops repeats across processes and restarts: the id is recorded in the same
    transaction as the handler's own writes (`tx`), so a handler that fails records nothing and is retried."""

    def __init__(self, name: str, handler: Handler, *, pool: DbPool | None = None, lru_size: int = 1024) -> None:
        self._name = name
        self._handler = handler
        self._pool = pool
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._lru_size = lru_size

    def _remember(self, event_id: str) -> None:
        self._seen[event_id] = None
        self._seen.move_to_end(event_id)
        while len(self._seen) > self._lru_size:
            self._seen.popitem(last=False)

    async def __call__(self, event: CloudEvent, tx: Any) -> None:
        if event.id in self._seen:
            return
        if self._pool is None:
            await self._handler(event, tx)
        elif isinstance(tx, Connection):
            if not await self._once(tx, event):
                return
        else:
            async with tenant_connection(self._pool, UUID(event.tenantid)) as conn:
                if not await self._once(conn, event):
                    return
        self._remember(event.id)

    async def _once(self, conn: Connection, event: CloudEvent) -> bool:
        """Record the id and run the handler in one savepoint, so a handler that raises records nothing. False
        when the event was handled before."""
        async with conn.transaction():
            if not await self._first_time(conn, event):
                self._remember(event.id)
                return False
            await self._handler(event, conn)
        return True

    async def _first_time(self, conn: Connection, event: CloudEvent) -> bool:
        row = await conn.fetchval(
            "INSERT INTO processed_events (tenant_id, consumer, event_id) VALUES ($1, $2, $3) "
            "ON CONFLICT DO NOTHING RETURNING 1",
            UUID(event.tenantid), self._name, event.id,
        )
        return row is not None

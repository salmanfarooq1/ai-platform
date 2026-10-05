# ADR 0008: The event bus and CloudEvents

**Status:** Accepted

## Context
Strict rule 9 asks for open standards, CloudEvents among them. Later sprints need to react to what the platform did: durable jobs and an outbox (Sprint 007), trust and receipts (008), and a Kafka adapter (010). Today the gateway writes one `gateway_decisions` row per call and tells nobody.

## Decision
- **A port.** `EventBus.publish(event, *, tx=None)` and `subscribe(type, handler)` in `ports/events.py`. A handler is `async def handler(event, tx)`. `"*"` subscribes to every type.
- **Events are CloudEvents 1.0.** `CloudEvent` is a frozen dataclass with `id`, `source`, `type`, `specversion` (only `1.0` is accepted), `time` (UTC), `subject`, `datacontenttype` and `data`, plus the extension attribute `tenantid`. `to_dict()` gives the JSON structured form. Type names are `platform.<area>.<thing>.v<major>`, so a breaking change to a payload is a new type.
- **The default adapter is in-process** (`adapters/inprocess_events.py`). `publish` awaits each handler in the publisher's task, in subscription order. It passes `tx` through, so a handler runs in the transaction context the caller gives. A handler that raises is logged and skipped: the other handlers still run, and the publisher is not failed by a subscriber.
- **The gateway publishes `platform.gateway.decision.v1`** after each decision row is written, inside the same transaction (`gateway/record.py` passes the connection as `tx`). `subject` is the decision id. `data` is `decision_id`, `outcome`, `stage`, `reason`, `action`, `resource`, `request_id` and `execution_id`. It never carries input text, and not the input hash either; a subscriber that needs more reads the decision row under row-level security.
- **A bus may fail the publisher.** An adapter that must not lose an event (the outbox in 007) raises from `publish`. Because the publish happens inside the record's transaction, the row is rolled back and `enforce()` turns an allow into a deny `decision_unrecorded` (503). A bus that fails therefore cannot let an action through unrecorded (strict rule 3). **A decision row is never lost because of the bus.** For a deny, the publish runs in a savepoint (`gateway/record.py`). If the bus raises, only the publish is rolled back. The deny row is committed, the error is logged and the call stays denied.
- **Contract.** `tests/contracts/test_event_bus_contract.py` runs against every adapter (type filtering, wildcard, order, `tx` pass-through, failure isolation, CloudEvent validity). The outbox and the Kafka adapter must pass it.

## Consequences
- Subscribers can be added without touching the gateway. The first real subscribers arrive in Sprint 007.
- Every governed call pays for the handlers it has, inside the request. The default bus has none.
- A subscriber that writes to the database through `tx` and fails with a database error aborts the decision's transaction, which fails closed. Subscribers should not do that unless they mean to be part of the record.
- Delivery with the in-process bus is at most once and only while the process lives. At-least-once delivery is the outbox's job.

## Alternatives considered
- **Publish after the commit:** a crash between the commit and the publish loses the event, which is what the outbox pattern exists to avoid. Publishing inside the transaction lets an outbox adapter commit with the decision.
- **A custom event format:** rejected for rule 9.
- **Putting the input hash in the payload:** rejected. A hash of a short input can be guessed, and subscribers do not need it.

## Outbox (Sprint 007)
The in-process bus delivers at most once. Sprint 007 adds the transactional outbox, which is the default adapter now (`EVENT_BUS=outbox`; `inprocess` is still available).
- **Write with the change.** `OutboxEventBus.publish(event, tx=conn)` inserts the event into the `outbox` table on the caller's connection (`adapters/pg_outbox_events.py`). It commits or rolls back with the state change that made it: a decision row, or a job marked succeeded. A rolled-back transaction leaves no event. With no `tx` the event gets a transaction of its own. The same event id twice is stored once (unique on tenant and event id).
- **Subscribers still run inline.** After the write, `subscribe`d handlers run in the publisher's task and get `tx`, as before. They are for work that must commit with the change. The bus passes the same contract suite as the other adapters.
- **A failed write fails the publisher.** The gateway rule is unchanged (M1): an allow whose outbox write fails is denied with 503 `decision_unrecorded` and its row rolls back. A deny publishes in a savepoint and keeps its row.
- **The relay publishes the rows** (`OutboxRelay`, run by `python -m workers` or by the API with `EMBEDDED_RELAY=true`). It lists unpublished rows, locks one (`FOR UPDATE SKIP LOCKED`), publishes it to a target `EventBus`, and marks it sent in the same transaction. The target is the in-process bus today and the Kafka adapter in Sprint 010. Several relays can run at once.
- **At least once.** A crash after the target got the event and before the mark commits sends it again. A failed send is counted (`attempts`) and tried on the next pass. After `OUTBOX_MAX_ATTEMPTS` the row is left for an operator.
- **Consumers dedupe by CloudEvent id.** `IdempotentConsumer` wraps a handler: an LRU stops repeats in one process, and the `processed_events` table (per tenant and consumer) stops them across restarts. The id and the handler's own writes share a savepoint, so a handler that raises records nothing.
- **Events written so far:** `platform.gateway.decision.v1` (every decision) and `platform.ingest.completed.v1` (a finished ingest job: ids, hash, status and chunk count, no text).
- **Workers and the relay are not tenants.** They find rows through three narrow SECURITY DEFINER functions (`jobs_claim`, `jobs_tenant_of_execution`, `outbox_pending`) that return only ids and tenants. Everything else runs under `tenant_connection` as `gap_app`. See ADR-0011.
- **Cost.** Every decision now writes one more row. There is no retention yet (Sprint 008): `outbox` and `processed_events` grow.

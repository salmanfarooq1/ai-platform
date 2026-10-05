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

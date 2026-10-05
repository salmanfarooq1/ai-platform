# Sprint 010: Kafka event bus adapter. Requirements

Infrastructure only, backend only.

## Scope
1. A Kafka EventBus adapter (`aiokafka`, Apache-2.0) selected by `EVENT_BUS=kafka`. The Postgres outbox stays the default.
   - The outbox relay can publish to Kafka.
   - Topics per event type. The key is the tenant id, so per-tenant order is kept.
   - CloudEvents use binary content mode in Kafka headers.
2. An optional compose profile `kafka` with Redpanda (single node) and the topic setup.
3. The adapter passes the shared EventBus contract suite. It runs against Redpanda when the image can be pulled, and otherwise against an in-memory Kafka fake. Record which.
4. Consumer groups with idempotent handling by CloudEvent `id`. A poison message goes to a dead-letter topic after N attempts.
5. A runbook `docs/runbooks/kafka.md` and `scripts/verify/kafka.sh` for a Linux or WSL machine.

# Sprint 010: Acceptance
- [ ] **A1.** All checks pass with 0 skipped. The Kafka adapter passes the EventBus contract suite (Redpanda or fake, recorded).
- [ ] **A2.** Outbox to Kafka end to end: a decision row leads to exactly one consumed event after dedupe, even when the relay is restarted mid-batch.
- [ ] **A3.** Per-tenant ordering holds over 1,000 events. A poison message lands in the dead-letter topic.
- [ ] **A4.** `docker compose --profile kafka config` is valid. A live Redpanda run is done here or marked "not verified here" with `scripts/verify/kafka.sh`.
- [ ] **A5.** Switching `EVENT_BUS` back to `outbox` needs no data migration.

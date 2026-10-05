# Sprint 010: Acceptance
- [x] **A1.** All checks pass with 0 skipped. The Kafka adapter passes the EventBus contract suite (Redpanda or fake, recorded).
- [x] **A2.** Outbox to Kafka end to end: a decision row leads to exactly one consumed event after dedupe, even when the relay is restarted mid-batch.
- [x] **A3.** Per-tenant ordering holds over 1,000 events. A poison message lands in the dead-letter topic.
- [x] **A4.** `docker compose --profile kafka config` is valid. A live Redpanda run is done here or marked "not verified here" with `scripts/verify/kafka.sh`.
- [x] **A5.** Switching `EVENT_BUS` back to `outbox` needs no data migration.

## Sign-off
Sprint 010 is accepted. The Architect re-ran the checks after the QA fixes:
- ruff, mypy and the DDL guard are clean, and the `kafka` compose profile is valid.
- Backend: 1568 passed. The only skips are the 10 live-MinIO runs.
- Frontend: 207 Vitest tests and 82 Playwright tests passed.

The live Redpanda run (`scripts/verify/kafka.sh`) passed 21 tests on one node. QA findings and their outcomes are in `qa-review.md`.

# Sprint 010: Report

Kafka event bus adapter. Infrastructure only, no UI change, no migration.

## Acceptance
| Check | Result | Evidence |
|---|---|---|
| **A1** All checks pass; the adapter passes the EventBus contract suite | Pass, with a caveat on "0 skipped". Ruff, mypy and `check_no_ddl.sh` are clean. Backend 1561 passed, 10 skipped. The 10 skips are the live-MinIO contract tests from earlier sprints, and `check_skips.py --expect 10` passes. The brief asks for exactly these 10, the acceptance text says 0 skipped: the 10 were not removed or changed. The Kafka adapter passes the contract suite on the in-memory broker (`kafka-fake`) in the normal run and on live Redpanda (`kafka-live`) in `kafka.sh`. | `ruff.txt`, `mypy.txt`, `check_no_ddl.txt`, `pytest-full.txt`, `check_skips.txt`, `kafka-live.txt` |
| **A2** Outbox to Kafka: one consumed event per decision after dedupe, relay restarted mid-batch | Pass, on both brokers. `tests/e2e/test_kafka_flow.py`: real app, decision rows, relay killed after the 3rd send (Kafka acknowledged, row not marked), a new relay finishes, a consumer group with Postgres dedupe handles each decision id once. The duplicate record is seen in the topic. Also `test_a_relay_killed_mid_batch...` in `tests/integration/test_kafka_bus.py`. | `kafka-live.txt`, `pytest-full.txt` |
| **A3** Per-tenant order over 1,000 events; poison message in the dead-letter topic | Pass, on both brokers. `test_1000_events_over_3_tenants_keep_each_tenants_order` (each tenant's sequence is exact, and on the fake each tenant sits on one partition). `test_a_poison_message_goes_to_the_dead_letter_topic_after_max_attempts...` (3 tries, `x-error` and `x-attempts` headers, the next message still runs, the offset is committed). A non-CloudEvent record also goes there at once. | `kafka-live.txt`, `pytest-full.txt` |
| **A4** `docker compose --profile kafka config` valid; live run done or marked | Pass. The config is valid (and the default config still is). The live run was done here: 16 tests on Redpanda v24.2.7 with `aiokafka` 0.14.0. | `compose-kafka-config.txt`, `redpanda-image.txt`, `kafka-live.txt`, `runbook-commands.txt` |
| **A5** Switch back to `outbox`, no data migration | Pass. No migration was added (a unit test checks the Alembic head is still `0010`). `test_switching_back_to_outbox_needs_no_data_migration`: rows written under `kafka` are sent by the same relay code to the in-process bus under `outbox`. | `pytest-full.txt` |

## Test numbers
- **Backend:** 1523 → 1561 passed (+38), 10 skipped (live MinIO, unchanged). New: 16 unit (`tests/unit/test_kafka_units.py`), 10 integration (`tests/integration/test_kafka_bus.py`), 2 e2e (`tests/e2e/test_kafka_flow.py`), 5 contract (the existing EventBus suite now also runs the Kafka adapter) and 5 import-lint (parametrised; `aiokafka` joins the banned-outside-adapters list).
- **Live (`scripts/verify/kafka.sh`):** 16 passed on Redpanda v24.2.7: 5 contract, 10 integration, 1 e2e. The other e2e test (switching back) has no broker part and runs in the normal suite.
- **Frontend (unchanged, run anyway):** 207 Vitest passed, 82 Playwright passed. `tokens:check`, lint, tsc and build pass. `chunk-report` and `copy-check` were not run (not in the brief's list).

## What was built
- `adapters/kafka_event_bus.py`: producer, binary content mode, consumer group, dedupe, dead-letter topic. Only module importing `aiokafka`.
- Settings and validation in `core/settings.py`; registry and relay wiring (`adapters/registry.py`, `workers/context.py`, `workers/__main__.py`, `workers/embedded.py`); `OutboxRelay.aclose`.
- `docker-compose.yml` profile `kafka` (Redpanda, topic job); `scripts/verify/kafka.sh`.
- `tests/fake_kafka.py` (murmur2 partitioner, offsets, committed offsets per group, redelivery of uncommitted records, ack after append) and `tests/kafka_helpers.py` (the same test body runs on the fake or, with `KAFKA_LIVE_BOOTSTRAP`, on a live broker; the id says which).
- Docs: ADR-0008 Kafka section, `docs/runbooks/kafka.md`, ARCHITECTURE, README section 18, `.env.example`, CHANGELOG, STATE, ROADMAP (010 done), QUESTIONS (Q41 to Q46, B15, B16), `build-log.md`.
- `pyproject.toml` pins `aiokafka (==0.14.0)`; `poetry.lock` updated.

## Deviations
1. **`EVENT_BUS=kafka` returns the outbox bus on the request path.** The blueprint selects the adapter with `EVENT_BUS=kafka` and also says Kafka is reached only by the relay. The registry therefore builds the outbox bus for the API, and the relay target is the Kafka bus. This follows the decision rule in the brief.
2. **`subscribe` and `consume` are separate.** `subscribe` is in-process (port meaning, needed for the shared contract suite). `consume` is the consumer-group path. The blueprint does not say how the two meet.
3. **Extra settings:** `KAFKA_SECURITY_PROTOCOL`, `KAFKA_MAX_ATTEMPTS`, `KAFKA_RETRY_BACKOFF_SECONDS` (Q46).
4. **A non-CloudEvent record goes to the dead-letter topic at once**, not after N attempts (retrying cannot help).
5. **`*` on `consume`** covers the three known platform types and types named in other `consume` calls (Q43).
6. **The pytest suite has a live param switch** (`KAFKA_LIVE_BOOTSTRAP`) instead of a separate skipped test, so nothing is skipped. By default only the fake runs.
7. **`poetry lock`** also added two packages `pyproject.toml` already listed (B16).
8. **Image registry:** the pinned image is pulled from Docker Hub (`redpandadata/redpanda`), because `docker.redpanda.com` was refused here.

## Open questions (in `planning/QUESTIONS.md`)
Q41 first consumer and its process. Q42 Redpanda licence review. Q43 wildcard list or pattern. Q44 attempt count across consumer restarts. Q45 topic retention. Q46 blueprint additions to confirm.

## Not verified here
SASL and TLS against a secured broker (settings and client options are unit-tested only); more than one broker; replication; several consumers in one group and rebalances; a broker restart during a run; a Kafka other than Redpanda; `docker.redpanda.com`; CI on GitHub; a Docker image build; `python -m workers` running the relay against a live broker (the relay's target construction was checked live by `evidence/runbook-commands.txt`, and the relay logic by the tests, but the worker process itself was not run with `EVENT_BUS=kafka`). The fake broker is a model, not a recording of a real run.

## Proposed commits (a human runs them; nothing was committed)
The working tree also holds uncommitted work from earlier sprints (see `planning/COMMIT_PLAN.md`), and the checked-out branch is `sprint/005-frontend-foundation`. Commit Sprint 010 on its own branch after the earlier blocks:
```bash
git switch -c sprint/010-kafka-event-bus
git add pyproject.toml poetry.lock core/settings.py adapters/kafka_event_bus.py adapters/registry.py adapters/pg_outbox_events.py \
  workers/context.py workers/__main__.py workers/embedded.py docker-compose.yml scripts/verify/kafka.sh
git commit -m "feat(events): Kafka EventBus adapter behind the outbox relay (ADR-0008)"
git add tests/fake_kafka.py tests/kafka_helpers.py tests/import_lint.py tests/contracts/test_event_bus_contract.py \
  tests/unit/test_kafka_units.py tests/integration/test_kafka_bus.py tests/e2e/test_kafka_flow.py
git commit -m "test(events): Kafka adapter on an in-memory broker and a live one"
git add docs/adr/0008-event-bus.md docs/runbooks/kafka.md docs/ARCHITECTURE.md README.md .env.example CHANGELOG.md \
  planning/STATE.md planning/ROADMAP.md planning/QUESTIONS.md planning/sprints/010-kafka-event-bus
git commit -m "docs: Sprint 010 Kafka event bus"
```
Add the attribution lines your commit policy requires.

## QA fixes
Backend 1561 → 1568 passed (+7), 10 skipped, `check_skips.py --expect 10` passes. Vitest 207, Playwright 82. Live `kafka.sh` repeated: 21 passed (`evidence/kafka-live.txt`). Ruff (including `sandbox_agent` and `scripts/eval`), mypy and the DDL guard are clean. Each fix was removed in turn and its test failed; the code was then restored.

| Finding | Fix | Test |
|---|---|---|
| H1 | `seek` added to the consumer protocol, the aiokafka wrapper and the fake. `poll_once` seeks back to the record on any failure of handling (dead-letter send, commit, cancel) and re-raises. | `test_a_failed_dead_letter_send_does_not_lose_the_poison_record` (fails without the seek). `test_a_failed_commit_replays_the_record_and_the_handler_runs_once` passes without it too: it guards the replay and dedupe, not the loss. |
| M1 | `x-error` is the class name, new `x-error-code` is `handler_failed` or `decode_failed`. The warning log has the class, no message, no `exc_info`. The decode test now checks the code, because the old `missing header` text is gone by design. | `test_the_error_header_and_the_log_carry_the_class_and_never_the_message` |
| M2 | `OutboxRelay.run_once` skips a tenant's later rows after its first failed or locked row. A row past max attempts is left for an operator and later rows then pass it (documented). | `test_the_relay_does_not_send_a_later_row_of_a_tenant_past_a_failed_one` |
| M3 | `FakeKafkaBroker.lost_acks`: the record is appended, then the send raises. Docs say order relies on sequential sends. | `test_a_send_that_was_applied_but_not_acknowledged_is_sent_again_and_handled_once` (also runs live, by wrapping the producer) |
| L1 | Stated in the runbook, the ADR and here: the live redelivery test replays through a new group, which is weaker than the fake's exact committed-offset reset. | none (documentation) |
| L2 | Settings `KAFKA_REQUEST_TIMEOUT_SECONDS` (10) and `KAFKA_SEND_TIMEOUT_SECONDS` (15, an `asyncio.wait_for` around the send). | `test_a_send_that_never_returns_fails_within_the_send_timeout`, `test_the_producer_limits_have_short_defaults_and_reach_the_client_options` |

Accepted without change: L3 (the runbook says to pin the image by digest on first pull), L4, L5. The ADR, runbook, `.env.example` and CHANGELOG are updated. Still not verified: the worker process with `EVENT_BUS=kafka`, SASL or TLS, several brokers and consumers.

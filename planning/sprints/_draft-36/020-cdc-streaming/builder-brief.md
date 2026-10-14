# Sprint 020: Builder brief
You are the Builder for Sprint 020 in /home/ubuntu/ai-platform, on branch `sprint/020-cdc-streaming`. This is infrastructure plus a small UI change. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 010 pack and report, `adapters/kafka_event_bus.py`, `tests/fake_kafka.py`, ADR-0008.
- Sprint 012 report (the `apache/kafka` service and the `cdc` profile), Sprint 015 report (`refco_source` and the change generator), Sprint 017 report (write lock).
- Q41, Q43, Q44, Q45 in `planning/QUESTIONS.md`.

## Build
1. Contract: `ports/cdc.py`, freshness on dataset responses, `GET /v1/data/cdc/sources`, OpenAPI snapshot.
2. Migration: next free number after Sprint 019's head.
3. `adapters/kafka_change_feed.py`, `dataplane/cdc/sink.py`, `workers/cdc_sink.py`.
4. Source setup SQL, connector JSON, Kafka SASL and ACL init, compose services, Postgres `wal_level`.
5. `scripts/admin/cdc.py`, `scripts/verify/cdc.sh`, WAL alert rule.
6. Freshness badge and Playwright test.
7. ADR-0017, runbook, docs. Answer Q41, Q43, Q44, Q45 in `planning/QUESTIONS.md` with the decisions in the blueprint.

## Tests
- Baseline: the numbers in Sprint 019's report. State the delta.
- pytest uses `tests/fake_cdc.py` on the in-memory broker. The live Kafka and Debezium run is `scripts/verify/cdc.sh` and its evidence, never a skipped pytest. If the images cannot be pulled here, mark the live checks "not verified here".
- The replay test injects a crash between the DuckLake commit and the Kafka commit, and between batch read and DuckLake commit.
- Every acceptance item and every threat row has a named test.

## Notes from the Architect
- `KafkaEventBus.consume` decodes CloudEvents and dead-letters anything else. Debezium envelopes are not CloudEvents, so the sink uses its own raw feed port. Reuse `KafkaConfig` and the SASL settings; do not copy them.
- The tenant never comes from a message. Not from a header, not from `source.db`, not from the key.
- Offsets live in the tenant's DuckLake catalog, in `_platform.cdc_offsets`, written in the same transaction as the data. Kafka's committed offset is never the source of truth.
- `ALTER TABLE ADD COLUMN` on DuckLake tables is inside ADR-0015's written exception. Build it from a validated column name and a mapped type, never from message text. Keep it in `dataplane/cdc/`; if `scripts/check_no_ddl.sh` scans that path, add a narrow, commented allowance for this one file and explain it in the report.
- Source DDL (role, publication, heartbeat table) belongs to the source database, not the platform schema. It lives in `data/reference-company/source/`.
- GitHub service containers cannot take a `command:`. Set `wal_level=logical` with `ALTER SYSTEM` and a container restart step.
- Pins: `quay.io/debezium/connect:3.6.2.Final`, `apache/kafka:4.3.1`, by digest. Re-check and save in `evidence/pins.txt`.
- No model or tool attribution in any file. No "demo" wording.

## Run
If Postgres or Valkey is down: `docker compose up -d --wait postgres valkey`, then `scripts/setup_db.sh`. Live: `docker compose --profile lake --profile cdc up -d --wait`, then `scripts/verify/cdc.sh`. Run, and save each output in `evidence/`:
- `poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`
- `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/020-cdc-streaming/evidence/pytest-int-e2e.xml`
- `poetry run python scripts/check_skips.py planning/sprints/020-cdc-streaming/evidence/pytest-int-e2e.xml` (the expected count comes from `tests/skip_allowlist.json`)
- `scripts/supply_chain/licence_gate.sh`
- `scripts/ci/edition_smoke.sh` (runs Gateway, Assurance, Agents, Data and Full)
- `docker compose --profile cdc config -q`
- `poetry run python scripts/update_openapi.py`
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check`
- `cd ui && npm run e2e`
- `docker stats --no-stream kafka debezium cdc-sink` under load

Script names come from `planning/program/conventions.md`. If a Builder had to change one, the change is recorded there. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- Simple sentences in docs. Docs change in lockstep (`CONTRIBUTING.md`).

## Finish
Write `report.md` with:
- the acceptance table with evidence links, and the threat-model test list;
- test numbers and the delta against Sprint 019's report;
- the migration number used; live or "not verified here" for A2, A3, A6; measured memory; deviations; open questions;
- proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, ops, docs, planning; merge small neighbours). Scopes: `cdc`, `db`, `ui`, `ops`, `ci`, `adr`, `planning`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit or push.

# Sprint 018: Builder brief
You are the Builder for Sprint 018 in /home/ubuntu/ai-platform, on branch `sprint/018-pipelines`. This is a vertical slice: contract, backend, UI, e2e. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 016 and 017 reports: the `QueryEngine` port, the write path and its advisory lock, the data scopes, the module registry.
- `workers/scheduler.py`, `core/database/jobs.py`, `migrations/versions/0009_trust_baseline.py` (purge functions to copy).
- `docs/design/IA.md` and `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
1. Contract: `ports/sources.py`, API models, OpenAPI snapshot (`poetry run python scripts/update_openapi.py`).
2. Migration: next free number after Sprint 017's head. Tables, RLS, GRANTs, `schedules_due`, purge functions.
3. Connectors and `adapters/egress.py`. Registry selection by `source_kind`.
4. Cron parser, scheduler pass, job kind registry, `pipeline_run` and `purge_platform` handlers.
5. Routes under `/v1/data/pipelines`, metrics.
6. Pipelines page and Playwright test.
7. ADR-0016, runbook, docs.

## Tests
- Baseline: the numbers in Sprint 017's report. State the delta.
- The contract suite runs every connector and the fake against the same tests.
- The Postgres connector test uses the throwaway database with a `refco_source` schema seeded by the Sprint 015 generator (small size).
- The HTTP connector test uses a local test server on an allowlisted name. The network guard fixture still blocks everything else.
- Cron tests use a fixed clock, never real time.
- Every acceptance item and every threat row has a named test.

## Notes from the Architect
- `workers/scheduler.py` today: one loop, `schedule_purges` only, interval `RETENTION_SCHEDULE_INTERVAL_SECONDS`. Keep its behaviour; add the schedules pass beside it.
- `USER_KINDS` in `core/database/jobs.py` drives what the job routes show. `pipeline_run` is user visible; `purge_platform` is not.
- `gap_app` has no DELETE on `jobs`, `outbox`, `processed_events`, `sandbox_events`, `run_tokens`. Purge through SECURITY DEFINER functions, exactly like `decisions_purge_batch`. Do not grant DELETE.
- `asyncpg` and `httpx` stay inside `adapters/` for connectors (import-lint). `dataplane/` calls the port.
- The load goes through Sprint 017's write path. Never open a second writer.
- No new dependency for cron. If you find one is needed, it must pass the licence gate; record why.
- Retention defaults are placeholders. Do not invent periods. Write them in `planning/QUESTIONS.md` against Q27 and Q35.
- No model or tool attribution in any file. No "demo" wording.

## Run
If Postgres or Valkey is down: `docker compose up -d --wait postgres valkey`, then `scripts/setup_db.sh`. Then run, and save each output in `evidence/`:
- `poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`
- `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/018-pipelines/evidence/pytest-int-e2e.xml`
- `poetry run python scripts/check_skips.py planning/sprints/018-pipelines/evidence/pytest-int-e2e.xml` (the expected count comes from `tests/skip_allowlist.json`)
- `scripts/supply_chain/licence_gate.sh`
- `scripts/ci/edition_smoke.sh` (runs Gateway, Assurance, Agents, Data and Full)
- `poetry run python scripts/update_openapi.py`
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check`
- `cd ui && npm run e2e`

Script names come from `planning/program/conventions.md`. If a Builder had to change one, the change is recorded there. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- Simple sentences in docs. Docs change in lockstep (`CONTRIBUTING.md`).

## Finish
Write `report.md` with:
- the acceptance table with evidence links, and the threat-model test list;
- test numbers and the delta against Sprint 017's report;
- the migration number used; deviations; open questions;
- proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, ops, docs, planning; merge small neighbours). Scopes: `pipelines`, `db`, `jobs`, `ui`, `adr`, `planning`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit or push.

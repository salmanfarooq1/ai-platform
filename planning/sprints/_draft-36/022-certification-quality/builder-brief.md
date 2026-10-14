# Sprint 022: Builder brief
You are the Builder for Sprint 022 in /home/ubuntu/ai-platform, on branch `sprint/022-certification-quality`. This is a vertical slice: contract, backend, UI, e2e. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 021 report and ADR-0018: products, contracts, lifecycle table, `data:steward`.
- Sprint 018 and 019 reports: the scheduler and the dbt runner. Sprint 020 report: `dataset_freshness`.
- `gateway/enforce.py` (`STAGES`), `gateway/stages.py`, `gateway/types.py` (`Action`), `gateway/reasons.py` and its catalogue test.

## Build
1. Contract: quality routes, API models, OpenAPI snapshot.
2. Migration: next free number after Sprint 021's head.
3. Gateway: `Action.context`, the `duties` stage on `product.certify` (from 021), two reason codes.
4. `dataplane/quality/`: auto-checks, contract rules, dbt test generation, profiling, score, evaluator job.
5. Schedules for certified and degraded products.
6. Quality page and Playwright test.
7. Docs and placeholders in `planning/QUESTIONS.md`.

## Tests
- Baseline: the numbers in Sprint 021's report. State the delta.
- Hysteresis is a pure-function table test: a sequence of scores in, a sequence of states out.
- The `duties` stage has unit tests with a fake context and integration tests through the real route.
- ydata-profiling runs for real on a small sample in the integration tier.
- Every acceptance item and every threat row has a named test.

## Notes from the Architect
- The gateway must not import `dataplane/` (import-linter). The route computes `context`; the stage only reads it.
- `context` is never filled from request input. Add a test that a body field named `context` has no effect.
- A new stage changes `STAGES`. The existing stage-order tests must still pass; add `duties` to them, do not loosen them.
- `ydata-profiling` is heavy (pandas, matplotlib). Put it in an optional group used by the worker image if the licence gate and image size allow; record the choice. Pin `4.18.4` after a re-check; save it in `evidence/pins.txt`.
- Contract rules of type `sql` are refused. Do not build a partial SQL guard here; 026 owns it.
- Do not invent weights or thresholds as business rules. Ship placeholders and list them in `planning/QUESTIONS.md`.
- No model or tool attribution in any file. No "demo" wording.

## Run
If Postgres or Valkey is down: `docker compose up -d --wait postgres valkey`, then `scripts/setup_db.sh`. For the lake: `docker compose --profile lake up -d --wait`. Run, and save each output in `evidence/`:
- `poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`
- `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/022-certification-quality/evidence/pytest-int-e2e.xml`
- `poetry run python scripts/check_skips.py planning/sprints/022-certification-quality/evidence/pytest-int-e2e.xml` (the expected count comes from `tests/skip_allowlist.json`)
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
- test numbers and the delta against Sprint 021's report;
- the migration number used; placeholders added to QUESTIONS; deviations; open questions;
- proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, docs, planning; merge small neighbours). Scopes: `quality`, `gateway`, `db`, `ui`, `planning`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit or push.

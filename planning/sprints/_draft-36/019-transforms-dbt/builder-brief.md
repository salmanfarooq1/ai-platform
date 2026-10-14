# Sprint 019: Builder brief
You are the Builder for Sprint 019 in /home/ubuntu/ai-platform, on branch `sprint/019-transforms-dbt`. This is a vertical slice: contract, backend, UI, e2e. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 016, 017 and 018 reports: locked connections, per-tenant catalog credentials, the write lock, pipelines and the scheduler.
- ADR-0015 and ADR-0016.

## Build
1. Contract: `transforms` on pipeline definitions, template catalogue route, OpenAPI snapshot.
2. Migration: next free number after Sprint 018's head (`lineage_raw_events`, `pipelines.transforms`).
3. `dataplane/transforms/`: templates, generator, package pre-check, profile writer, `dbt_run` handler.
4. Vendor the packages the templates need (if any) and write `packages.lock`. If no template needs a package, ship one small allowlisted package used by a test fixture only.
5. Run the OpenLineage spike on `spike/019-openlineage-dbt`. Wire the passing path or the fallback.
6. UI: transform steps in the pipeline editor and run timeline.
7. ADR-0016 dbt section, runbook, docs.

## Tests
- Baseline: the numbers in Sprint 018's report. State the delta.
- dbt runs for real in the integration tier, against a temporary DuckLake on the throwaway Postgres (no fake: the template test pattern says DuckDB needs none).
- Keep the integration runs small (reference company small size) so the tier stays fast.
- Every acceptance item and every threat row has a named test.

## Notes from the Architect
- Pins: `dbt-core==1.12.5`, `dbt-duckdb==1.11.0`, `openlineage-dbt==1.53.0` (spike only unless it passes). Re-check each and save the result in `evidence/pins.txt`. dbt-duckdb must accept the `duckdb==1.5.5` pin; if it does not, stop on this item and log it.
- Add `dbt`, `dbt.adapters.duckdb` and `openlineage` to the import-lint SDK list: only `dataplane/transforms/` runner code may import them, and only through the subprocess boundary where possible.
- Merge incremental on DuckLake is the main technical risk. If `incremental_strategy='merge'` does not work on DuckLake at this pin, use `delete+insert` and record the deviation.
- dbt runs DDL on DuckLake tables. That is inside ADR-0015's written exception to strict rule 7. Platform tables still change only through Alembic. Template files hold SELECT only, so `scripts/check_no_ddl.sh` stays clean.
- No user SQL. If any part of the work seems to need it, that is a stop condition.
- Never write secrets to disk, even in a temp dir. Use `env_var()`.
- No model or tool attribution in any file. No "demo" wording.

## Run
If Postgres or Valkey is down: `docker compose up -d --wait postgres valkey`, then `scripts/setup_db.sh`. For the lake: `docker compose --profile lake up -d --wait`. Run, and save each output in `evidence/`:
- `poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`
- `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/019-transforms-dbt/evidence/pytest-int-e2e.xml`
- `poetry run python scripts/check_skips.py planning/sprints/019-transforms-dbt/evidence/pytest-int-e2e.xml` (the expected count comes from `tests/skip_allowlist.json`)
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
- test numbers and the delta against Sprint 018's report;
- the migration number used; the spike result; deviations (merge strategy); open questions;
- proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, ops, docs, planning; merge small neighbours). Scopes: `pipelines`, `db`, `lake`, `ui`, `adr`, `planning`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit or push.

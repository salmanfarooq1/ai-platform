# Sprint 021: Builder brief
You are the Builder for Sprint 021 in /home/ubuntu/ai-platform, on branch `sprint/021-data-products-contracts`. This is a vertical slice: contract, backend, UI, e2e. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, `planning/DOMAIN.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 016 and 017 reports: datasets, schema versions, `QueryEngine`, data scopes.
- `gateway/boundary.py` (`SCOPE_ACTIONS`), `gateway/types.py` (`ActionKind`), `gateway/reasons.py`, `core/identity/models.py` (`Scope`), `gateway/policy.py` (`_has_foreign_ref`, to reuse for aspect types).
- The ODPS 1.1.0 and ODCS 3.2.0 specifications (vendor their JSON Schemas).

## Build
1. Contract: API models, routes, OpenAPI snapshot.
2. Migration: next free number after Sprint 020's head. Seed `product_lifecycle_transitions`.
3. Scope `data:steward`, action kind `product.certify`, boundary mapping. Update the reason-code and scope docs. Record in the report that `product.certify` starts here, so `planning/program/conventions.md` can say 021.
4. `dataplane/products/`: validate, diff, lifecycle, search, glossary, aspects.
5. Reference finance product and contract in `data/reference-company/products/`.
6. Products page and Playwright test.
7. ADR-0018, `docs/contracts/products.md`, `planning/DOMAIN.md`.

## Tests
- Baseline: the numbers in Sprint 020's report. State the delta.
- The diff test is table-driven: one row per change kind with the expected level.
- `datacontract-cli` runs for real in the unit tier on fixture files. The network guard stays on.
- Every acceptance item and every threat row has a named test.

## Notes from the Architect
- Pin `datacontract-cli` after a re-check (`1.2.4` is the starting point). Its `duckdb` extra must resolve to `duckdb==1.5.5`. If it forces another DuckDB, install it without the extra and use only lint; record that. Save the result in `evidence/pins.txt`.
- `datacontract-cli` must never get catalog or S3 credentials. The schema test reads the dataset schema through the `QueryEngine` port.
- Contract versions are immutable. The migration grants SELECT and INSERT only. Do not add UPDATE to make a test easier.
- The lifecycle table is reference data with no tenant column. It is read-only for `gap_app`.
- A new scope changes the identity CLI help, `docs/api/README.md` and `docs/configuration.md`. Update all three.
- No model or tool attribution in any file. No "demo" wording.

## Run
If Postgres or Valkey is down: `docker compose up -d --wait postgres valkey`, then `scripts/setup_db.sh`. For the lake: `docker compose --profile lake up -d --wait`. Run, and save each output in `evidence/`:
- `poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`
- `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/021-data-products-contracts/evidence/pytest-int-e2e.xml`
- `poetry run python scripts/check_skips.py planning/sprints/021-data-products-contracts/evidence/pytest-int-e2e.xml` (the expected count comes from `tests/skip_allowlist.json`)
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
- test numbers and the delta against Sprint 020's report;
- the migration number used; the `datacontract-cli` pin and extra outcome; deviations; open questions;
- proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, docs, planning; merge small neighbours). Scopes: `products`, `db`, `gateway`, `ui`, `adr`, `planning`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit or push.

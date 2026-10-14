# Sprint 024: Builder brief
You are the Builder for Sprint 024 in /home/ubuntu/ai-platform, on branch `sprint/024-query-enforcement`. This is a vertical slice: contract, backend, UI, e2e. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- ADR-0015 and the Sprint 016 report: locked connections, snapshot pinning, the query worker.
- Sprint 021, 022 and 023 reports: classification, `Action.context`, the `duties` stage, grants, purposes, row filters.
- `gateway/enforce.py`, `gateway/stages.py`, `gateway/policy.py` (`PolicyDocument`), `gateway/reasons.py`.
- `planning/program/vision-and-architecture.md`, lakehouse design: grants by rewriting, never by views.

## Build
1. Contract: `POST /v1/data/query`, API models, OpenAPI snapshot.
2. `dataplane/query/`: rewrite, masks, row filters, group size, cache keys, watchdog.
3. Gateway: `purpose` stage, `query` stage reasons, `mask_policy` on `PolicyDocument`, record extensions.
4. The bypass corpus and its runner first, then make it pass.
5. Data query page and Playwright test.
6. ADR-0019 and docs.

## Tests
- Baseline: the numbers in Sprint 023's report. State the delta.
- Write the corpus before the rewrite. Each case names its expected outcome. Never edit an expectation to make it pass without a note in the report saying why the expectation was wrong.
- The pruning test uses a real DuckLake table partitioned by month on the throwaway Postgres.
- The revoke test starts a slow query (a large `range()` join on the granted relation), revokes, and checks the interrupt.
- Every acceptance item and every threat row has a named test.

## Notes from the Architect
- Pin sqlglot exactly after a re-check (MIT, a release at least two weeks old). Save it in `evidence/pins.txt`. Parse with `read="duckdb"`; generate with `dialect="duckdb"`.
- Never build SQL by string concatenation. Build sqlglot nodes; bind values.
- DuckDB views are not a security boundary. Do not use them for grants.
- The physical table name and catalog come from the server, never from the SQL.
- The `query` stage reasons are decided in `dataplane/` before `enforce()`. Pass the outcome in `context`, so the deny is a recorded decision. The gateway still imports no `dataplane/` code.
- The purpose stage must be behaviour-identical when OPA replaces it in 031. Keep its logic small and table-tested.
- Mask defaults, the default k and the query limits are placeholders. Each is a setting with a default. Write them in `planning/QUESTIONS.md`.
- Over-limit queries are denied. Do not add an approval path; 034 owns it.
- No model or tool attribution in any file. No "demo" wording.

## Run
If Postgres or Valkey is down: `docker compose up -d --wait postgres valkey`, then `scripts/setup_db.sh`. For the lake: `docker compose --profile lake up -d --wait`. Run, and save each output in `evidence/`:
- `poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`
- `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/024-query-enforcement/evidence/pytest-int-e2e.xml`
- `poetry run python scripts/check_skips.py planning/sprints/024-query-enforcement/evidence/pytest-int-e2e.xml` (the expected count comes from `tests/skip_allowlist.json`)
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
- test numbers and the delta against Sprint 023's report; corpus size by category;
- migrations (none expected; say so, or the number used); deviations; open questions;
- proposed commit blocks per `planning/program/branching-and-commits.md` (contract, code, tests, UI, docs, planning; merge small neighbours). Scopes: `access`, `lake`, `gateway`, `ui`, `adr`, `planning`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit or push.

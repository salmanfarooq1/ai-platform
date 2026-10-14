# Sprint 026: Builder brief
You are the Builder for Sprint 026 in `/home/ubuntu/ai-platform`, on branch `sprint/026-semantic-layer-query-guard`. This is a vertical slice: spike first, then the contract, backend, UI and an e2e test. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md` and `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md` and `threat-model.md`.
- `planning/program/vision-and-architecture.md`: target request path steps 4 to 7.
- The reports of Sprints 016, 019, 024 and 025. Read the 024 rewrite and bypass corpus closely.
- `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
1. **Spike.** Run it on `spike/026-metricflow`, cut from the sprint branch. Do not merge it. Copy the result into `evidence/spike-metricflow.md`, then choose the path.
2. **Then build the blueprint:** contract, `dataplane/semantic/`, reason codes and the guard verdict in the 024 `query` stage, semantic models for the reference marts, routes, UI.

## Tests
- **Baseline:** the numbers in Sprint 025's report. State the delta.
- Write one test per acceptance item and per threat-model row, using the names given there.
- **Fuzz corpus:**
  - At least 50 cases, each with an expected reason code.
  - Cover: stacked statements, comments, quoted identifiers, unicode look-alikes, nested subqueries, CTE shadowing of a table name, table functions, `COPY` and `EXPORT`, case tricks, and parser differentials.
- Expected metric results come from the deterministic 015 generator output, computed in plain Python in the test. Do not compute them with DuckDB.
- No live verify script is needed: DuckDB runs in process. Add no new skips.

## Notes from the Architect
- **Pins:** `dbt-metricflow==0.15.0`, which needs dbt-core ≥1.11 and <1.13. Re-check it with dbt-core 1.12.5 and `duckdb==1.5.5`, and record the result in `evidence/pins.txt`. If it forces another DuckDB version, it fails the spike.
- **Compile only.** Never let MetricFlow open a data connection to the lakehouse. Use its explain or compile output only.
- **Execute generated SQL.** Run the SQL that sqlglot generates from the guarded tree, never the compiler's original text.
- **Guard placement:** the guard runs before the rewrite (on tables and functions) and after it (on the final SQL). The seed says "compile, then rewrite, then guard". Pass 2 meets that; pass 1 is extra defence.
- **Boundaries:** `dataplane/` must not import `gateway/`. It passes its verdict in the action `context`, and the 024 `query` stage records it.
- **Over the limit is a deny.** Do not add "approval required" here (034).
- **Migration:** none expected. If one is needed, use the next free number after Sprint 025's head.
- **Docs:** update ADR-0021, `docs/architecture.md`, the API docs, `.env.example` (the three limits), the OpenAPI snapshot, CHANGELOG (with the test delta), STATE and DECISIONS (the spike result).

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/026-semantic-layer-query-guard/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/026-semantic-layer-query-guard/evidence/pytest-int-e2e.xml   # expected count from tests/skip_allowlist.json
scripts/supply_chain/licence_gate.sh   # dbt-metricflow and its dependencies must pass
scripts/ci/edition_smoke.sh
poetry run python scripts/update_openapi.py
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Script names come from `planning/program/conventions.md`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names, no model or tool attribution. Use simple sentences in docs.

## Finish
Write `report.md` with:
- the acceptance table with evidence links
- the test numbers and the delta against Sprint 025
- the spike outcome and the migration (or "none")
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(semantic): add semantic metrics and query contract`
- `feat(semantic): compile metrics and guard parsed sql before and after rewrite`
- `test(semantic): add injection fuzz corpus and hand-computed metric checks`
- `feat(ui): add metrics panel to ask page`
- `docs(adr): record semantic layer and guarded sql`
- `docs(planning): update state, decisions and changelog for the semantic layer`

The Builder does not commit. A human runs the commands.

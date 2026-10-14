# Sprint 028: Builder brief
You are the Builder for Sprint 028 in `/home/ubuntu/ai-platform`, on branch `sprint/028-governed-dashboards`. This is a vertical slice: contract, backend, UI and an e2e test. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md` and `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md` and `threat-model.md`.
- `planning/program/vision-and-architecture.md`: modules, editions and design rule 1.
- The reports of Sprints 013 (module registry, ports), 016 (snapshots, `DataAccess`), 021, 022, 024 (rewrite, purpose, cache), 025 (`LineageEmitter`, `LineageLookup`), 026 (semantic path) and 027 (answer receipts).
- `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
1. Module registry entry, package skeleton, import-linter contract for `insights/`.
2. Contract and spec schema, then the catalog, then render, then dashboards.
3. UI: Metrics, Explore, Dashboards, tile drawer, "Pin to dashboard" on the Ask page.

## Tests
- **Baseline:** the numbers in Sprint 027's report. State the delta.
- One test per acceptance item and per threat-model row, using the names given there.
- Expected numbers come from the 026 hand-computed result sets. Do not compute them with DuckDB.
- No live verify script: DuckDB runs in process. Add no new skips.

## Notes from the Architect
- **Pins:** `vega-lite@6.4.1`, `vega@6.2.0` and `vega-embed@7.3.0` (all BSD-3; the same Vega-Lite and Vega builds that vl-convert 1.9.0 bundles). Check that `npm run chunk-report` stays inside the budget; load charts lazily if needed.
- **No author rights.** Never render a tile with a service identity. The worker or request always carries the viewer's principal.
- **Same path as the agent.** Tiles call `DataAccess` like the 027 tools. Do not add a second query path. Do not import `dataplane/` from `insights/`.
- **One snapshot per view.** Call `DataAccess.current_snapshot` once, then pass that `snapshot_id` to every tile query.
- **No tile cache.** Rely on the 024 cache behind `enforce()`.
- **Charts:** build the Vega-Lite spec in `insights/charts.py`. The UI passes it to `vega-embed` with a loader that refuses every URL.
- **Placeholders:** the three limits are settings with defaults. Log one question each.
- **Migration:** next free number after Sprint 027's head.
- **Docs:** ADR-0031, `docs/architecture.md`, `docs/design/IA.md`, the API docs, `.env.example`, the OpenAPI snapshot, CHANGELOG (with the test delta), STATE and DECISIONS.

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/028-governed-dashboards/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/028-governed-dashboards/evidence/pytest-int-e2e.xml   # expected count from tests/skip_allowlist.json
scripts/supply_chain/licence_gate.sh
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
- the test numbers and the delta against Sprint 027
- the migration number
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(insights): add insights module, metric catalog and dashboard contract`
- `feat(insights): render dashboards under the viewer's grants with one snapshot per view`
- `feat(ui): add metrics, explore and dashboards pages`
- `test(insights): add viewer rights, purpose and snapshot consistency tests`
- `docs(adr): record governed bi on the semantic layer`
- `docs(planning): update state, decisions and changelog for dashboards`

**Freeze point:** say in the report that after merge, a human tags `main` as `v0.28.0`. This is the proposed command: `git tag -a v0.28.0 -m "freeze point: source row to signed answer and governed dashboard" && git push origin v0.28.0`. Add a `CHANGELOG.md` section with the test delta, migrations, new services and measured memory.

The Builder does not commit or tag. A human runs the commands.

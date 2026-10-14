# Sprint 016: Builder brief
You are the Builder for Sprint 016 in /home/ubuntu/ai-platform, on branch `sprint/016-lakehouse-read-path`. Vertical slice, M4: the lakehouse read path, from the contract to the Data > Datasets page. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, `docs/architecture.md` section 2, ADR-0013.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `planning/program/vision-and-architecture.md` (Lakehouse design) and the Sprint 015 report.
- `gateway/types.py`, `gateway/boundary.py`, `gateway/policy.py`, `gateway/reasons.py`, `core/modules.py`, `evidence/extensions.py`, `tests/import_lint.py`, `tests/harness.py`, `scripts/setup_db.sh`, `Dockerfile`.
- `.claude/skills/governed-design/SKILL.md` before any UI code.

## Build
Start with a spike on `spike/016-ducklake-lock` (never merged): prove the setup order (load, secret, attach, then the lock) on DuckDB 1.5.5 with a Postgres catalog and a SeaweedFS data path. Save the result in `evidence/spike-lock.txt`. Then: contract and OpenAPI, migration, port and adapter with the contract suite, gateway, routes, worker handler, UI, verify script, docs. Write a short plan in `build-log.md` first.

## Tests
- **Baseline:** the numbers in Sprint 015's report.
- Pytest runs DuckLake on a throwaway `lakehouse` database (next to the throwaway platform database in `tests/harness.py`) with a temp local data path. No S3 in pytest.
- The live SeaweedFS run is `scripts/verify/ducklake.sh`, never a skipped pytest.
- The isolation cases run against the locked connection directly and through the API.

## Notes from the Architect
- **Code facts:**
  - `gateway/types.py` `ActionKind` has no data kind. `SCOPE_ACTIONS` gives `admin` every kind automatically.
  - Scopes live in the `Scope` enum in `core/identity/models.py`; `ALL_SCOPES` and the identity CLI read it. Add `data:read` there.
  - A tenant policy that leaves out a list allows nothing; `DEFAULT_POLICY` uses `"*"` for every list. Follow the same pattern for `allowed_datasets`.
  - `KNOWN_TOOLS` lists MCP and agent tool names for `tool_arguments`. No data tool exists yet, so leave it unchanged and say so in the report.
  - `scripts/setup_db.sh` creates only `rag_platform`. `tests/harness.py` creates the throwaway database at line 99.
  - Extensions are fetched from the network by default. The network guard blocks that in tests. Install them once into `DUCKDB_EXTENSION_DIR` (a CI step and the Dockerfile), never at runtime.
- **Traps:**
  - Set `allow_unsigned_extensions` at instance start (it cannot be set later). Attach before `enable_external_access=false`, or the attach fails.
  - If SeaweedFS cannot limit an identity to a prefix, use one bucket per tenant instead. Record which in ADR-0015.
  - DuckDB has no statement timeout. Use `interrupt()` from a timer.
- **Pins:** `duckdb==1.5.5`; DuckLake spec 1.0 extension version matched to it. Save in `evidence/pins.txt`. Run the licence gate.
- **Migration:** the next free number after the previous sprint's head (0010 at the start of 011). `GRANT SELECT ON lakehouse_catalogs TO gap_app`.
- **ADR-0015:** per-tenant DuckLake catalogs, locked connections, gateway-only access, and the strict rule 7 exception for DuckLake's own catalog tables.

## Run
```bash
poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
poetry run lint-imports
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/016-lakehouse-read-path/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/016-lakehouse-read-path/evidence/pytest-int-e2e.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python scripts/update_openapi.py
scripts/verify/ducklake.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Add `dataplane` to the mypy file list. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs. Catalog and S3 secrets by env var or mounted file only.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1 to A7, A-sec, A-mem) with links to `evidence/`
- test numbers and the delta against Sprint 015's report
- the migration number taken, and the spike result
- deviations and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md` (the Sprint 016 example there): contract (`ports/query_engine.py`, `api/models/data.py`, `docs/api/openapi.json`, `feat(lake)`), migration (`feat(db)`), code (`dataplane/`, `adapters/duckdb_engine.py`, `adapters/registry.py`, `core/`, `gateway/`, `evidence/extensions.py`, `api/routers/data.py`, `workers/`, `feat(lake)`), tests (`test(lake)`), UI (`feat(ui)`), ops (`Dockerfile`, `scripts/`, `.github/`, `chore(ops)`), docs (`docs(adr)`), planning (`docs(planning)`), each with its `git add` paths, then the push and `gh pr create --base main` commands.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.

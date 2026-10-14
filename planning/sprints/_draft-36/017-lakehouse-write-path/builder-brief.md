# Sprint 017: Builder brief
You are the Builder for Sprint 017 in /home/ubuntu/ai-platform, on branch `sprint/017-lakehouse-write-path`. Vertical slice, M4: the dataset registry, uploads through jobs, maintenance, erasure, the seed load and the Data page. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, ADR-0011, ADR-0015.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- The Sprint 016 report and `planning/program/vision-and-architecture.md` (Lakehouse design).
- `adapters/duckdb_engine.py`, `dataplane/`, `api/routers/data.py`, `api/routers/ingest.py` (202 with a job, raw file by SHA-256), `core/database/jobs.py`, `workers/scheduler.py`, `workers/handlers/purge.py`, `data/reference-company/`.
- `.claude/skills/governed-design/SKILL.md` before any UI code.

## Build
Order: contract and OpenAPI; migration; writer lock and upload job with the limits; schema versions; maintenance and scheduler; erasure; seed load; UI; docs. Write a short plan in `build-log.md` first.

## Tests
- **Baseline:** the numbers in Sprint 016's report.
- Pytest uses the throwaway `lakehouse` database and a temp data path (as in 016). Concurrency tests run two real worker loops in one test.
- Provoke the DuckLake conflict with a second connection that skips the lock, only inside the test.
- The live SeaweedFS run extends `scripts/verify/ducklake.sh` with an upload, maintenance and an erasure.

## Notes from the Architect
- **Code facts:**
  - `jobs.kind` is free text (`CHECK (kind <> '')`), so new kinds need no constraint change. `USER_KINDS` controls what the job routes show: add `lake_upload` and `lake_erasure`, not `lake_maintenance`.
  - `workers/scheduler.py` only queues `purge_decisions`, through `retention_due_tenants`. Add `schedule_lake_maintenance` beside it; do not build the generalised scheduler (018).
  - Raw uploads are stored by SHA-256 through the `ObjectStore` port, as ingest does.
  - Decision rows carry `extensions.data.table` and `snapshot_id` since 016.
- **Decided:**
  - Lock key is the dataset id, as the seed says. Held on one session for the whole write.
  - Protected snapshots are derived from decision rows, not stored, so a read never writes.
  - Retention, replay-window and upload-limit defaults are placeholders. Each is a setting with a default. Write them in `planning/QUESTIONS.md` for an owner.
  - The `{id}` change is a deliberate break of the 016 contract. Update the 016 route tests to the new paths, and say so in the report.
- **Strict rule 6:** erasure deletes raw upload objects that held erased rows. Write this as a question in `planning/QUESTIONS.md` and as a section in ADR-0015. If QA rejects it, the fallback is to keep the raw file and mark the erasure "partial" with the object hash.
- **Q27 and Q35:** do them only if the scheduler work is done and green. Otherwise write "moved to 018" in the report.
- **Migration:** the next free number after the previous sprint's head (0010 at the start of 011). Grant `gap_app` only what it needs per table.

## Run
```bash
poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/lake
poetry run mypy
poetry run lint-imports
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/017-lakehouse-write-path/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/017-lakehouse-write-path/evidence/pytest-int-e2e.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python scripts/update_openapi.py
scripts/verify/ducklake.sh
poetry run python scripts/lake/seed_reference_company.py --size small
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs. Writer keys only in the worker's mounted file.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1 to A7, A-sec, A-mem) with links to `evidence/`
- test numbers and the delta against Sprint 016's report
- the migration number taken
- whether Q27 and Q35 were done or moved to 018
- deviations and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md`: contract (`api/models/data.py`, `docs/api/openapi.json`, `feat(lake)`), migration (`feat(db)`), code (`dataplane/`, `adapters/`, `api/routers/data.py`, `workers/`, `core/`, `gateway/`, `feat(lake)`), tests (`test(lake)`), UI (`feat(ui)`), ops (`scripts/lake/`, `scripts/admin/lakehouse.py`, `scripts/verify/ducklake.sh`, `chore(ops)`), docs (`docs(adr)`, `docs(ops)`), planning (`docs(planning)`), each with its `git add` paths, then the push and `gh pr create --base main` commands.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.

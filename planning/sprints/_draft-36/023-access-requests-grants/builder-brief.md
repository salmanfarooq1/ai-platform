# Sprint 023: Builder brief
You are the Builder for Sprint 023 in /home/ubuntu/ai-platform, on branch `sprint/023-access-requests-grants`. This is a vertical slice: contract, backend, UI, e2e. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, `planning/DOMAIN.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 021 and 022 reports: products, lifecycle, `data:steward`, the separation-of-duties check, `Action.context`.
- Sprint 017 report: extracts, CSV neutralising, object store prefixes. Sprint 018 report: the scheduler.
- `core/database/tenant.py` (`tenant_connection`), the policy version pattern in `gateway/policy.py`, and the SECURITY DEFINER functions in migrations `0008` and `0009`.
- `planning/program/reference-data-portal.md`: the "what we avoid" list for approvals and grants.

## Build
1. Contract: `/v1/access` and `/v1/approvals` routes, API models, OpenAPI snapshot.
2. Migration: next free number after Sprint 022's head. RLS for two tenant columns, `access_request_create`, `listings_visible_to`, `grant_create`.
3. Gateway: four action kinds, the shared `duties` stage, the `grant` stage, three reason codes.
4. `dataplane/access/`: listings, requests, hash, approvals, grant worker, expiry job, revocation, extracts.
5. Seed for the reference company: groups, purposes, approval policy, one listing.
6. Marketplace, My access and Approvals pages; Playwright across two personas.
7. Docs.

## Tests
- Baseline: the numbers in Sprint 022's report. State the delta.
- Race tests use two real connections and `asyncio.gather`, not mocks.
- Cross-tenant tests use the `tenants` fixture (two tenants).
- Presigned URL tests use the Sprint 012 object store test setup; the live check stays in `scripts/verify/seaweedfs.sh`.
- Every acceptance item and every threat row has a named test.

## Notes from the Architect
- "Approved" is not "granted". Only `grant_create` makes a grant. Do not give `gap_app` INSERT on `grants`.
- Approval is bound to the request hash. Define the canonical JSON once (sorted keys, no spaces, UTF-8) and reuse it in 034.
- Extending the `duties` stage (022) to `access.approve` must keep every Sprint 022 test green unchanged.
- Approvals live at `/v1/approvals` with a `kind` field and one `approvals` table. Keep the kind handling generic (a small registry of kinds), so 034 adds a kind without changing the route or the table shape.
- Expiry is checked on every use. The job only tidies state.
- Cross-tenant grants deliver data through extracts only in this sprint. Do not attach another tenant's catalog anywhere; that would break ADR-0015.
- Groups live in the platform until 035. Keep the group model small.
- No model or tool attribution in any file. No "demo" wording.

## Run
If Postgres or Valkey is down: `docker compose up -d --wait postgres valkey`, then `scripts/setup_db.sh`. For the lake: `docker compose --profile lake up -d --wait`. Run, and save each output in `evidence/`:
- `poetry run ruff check api core gateway evidence dataplane ports adapters workers sandbox_agent tests scripts/e2e scripts/docs`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`
- `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/023-access-requests-grants/evidence/pytest-int-e2e.xml`
- `poetry run python scripts/check_skips.py planning/sprints/023-access-requests-grants/evidence/pytest-int-e2e.xml` (the expected count comes from `tests/skip_allowlist.json`)
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
- test numbers and the delta against Sprint 022's report;
- the migration number used; deviations; open questions;
- proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, docs, planning; merge small neighbours). Scopes: `access`, `gateway`, `db`, `ui`, `planning`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit or push.

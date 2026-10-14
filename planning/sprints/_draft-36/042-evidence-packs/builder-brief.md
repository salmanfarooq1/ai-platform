# Sprint 042: Builder brief
You are the Builder for Sprint 042 in /home/ubuntu/ai-platform, on branch `sprint/042-evidence-packs`. A vertical slice in module M2: contract first, then backend, then UI, then e2e. Work autonomously. Stop conditions are in AGENTS.md. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, `docs/design/IA.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 041's `report.md`, ADR-0012, ADR-0029, ADR-0030.
- The decision list query (`GET /v1/decisions`), the purge function and its migration, the approvals, oversight and incident tables (034, 039), `insight_runs` with report manifests (029), eval runs (008).
- `.claude/skills/governed-design/SKILL.md` before any UI code.

## Build
Everything in the blueprint. Order: contract and OpenAPI, migration, pack builder and job, search and export, verifier `pack` subcommand, UI pages, docs. Search reuses the decision list query; do not write a second one.

## Tests
- Baseline: the numbers in Sprint 041's report.
- The fake TSA and in-memory object store from earlier sprints. No live service is needed for pytest.
- The reference company (medium size) is the fixture for A2, A4 and A7.
- Each acceptance item and each threat row has a named test.

## Notes from the Architect
- **System:** this sprint introduces `ai_systems` and `ai_system_principals` as in the blueprint. No earlier sprint holds a list of systems (039 has only the free-text `incidents.system`, linked here). Log the definition in `planning/DECISIONS.md`. Sprints 043 and 045 reference `ai_systems`.
- **Retention floor:** the cutoff stays inside `decisions_purge_batch`. The caller never passes the floor. The 183-day default comes from EU AI Act Art. 19 and 26 (at least six months); write that in the migration comment. It is a placeholder: log a question in `planning/QUESTIONS.md` and do not present it as an agreed rule.
- **No content:** a pack is built from records. Never read a prompt, answer or document body. Free-text fields become SHA-256.
- **Signing:** the manifest is a COSE_Sign1 statement signed with the receipt key (`kid`). The checkpoint key and TSA key are not used for it.
- **Migration:** the next free number after Sprint 041's head. Forward only, tested from the previous head.
- **Edition:** the Assurance edition has no M5. The lineage summary must come through the port and say `not linked` there. The edition smoke set builds a pack.

## Run
If Postgres, Valkey or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run python scripts/update_openapi.py
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/042-evidence-packs/evidence/junit.xml
poetry run python scripts/check_skips.py planning/sprints/042-evidence-packs/evidence/junit.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names for the platform, no model or tool attribution.
- Short, simple sentences in docs and UI copy.

## Finish
Write `report.md` and `evidence/`. The report has: the acceptance table with evidence links, test numbers and the delta against Sprint 041, the migration number, deviations, open questions, and proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, ops, docs, planning). No commits by the Builder. Update `planning/STATE.md` and `CHANGELOG.md`.

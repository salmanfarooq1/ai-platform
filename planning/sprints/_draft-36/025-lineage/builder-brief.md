# Sprint 025: Builder brief
You are the Builder for Sprint 025 in `/home/ubuntu/ai-platform`, on branch `sprint/025-lineage`. This is a vertical slice: contract first, then backend, then UI, then an e2e test across both. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md` and `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md` and `threat-model.md`.
- `planning/program/vision-and-architecture.md`: the cross-module ports, and design rule 5 ("lineage is evidence").
- The reports of Sprints 018, 019, 020 and 024. Sprint 019's report says where the raw OpenLineage events and the spike result are.
- The `LineageEmitter` and `EvidenceLookup` ports in `ports/`, and `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
Build everything in the blueprint in this order: contract and facet schemas, migration, `lineage/` (store, emitter, consumer, redaction), emit points in the 018, 019 and 020 code, routes, the 022 auto-check, UI. Then replay the raw dbt events stored by 019 through the same consumer.

## Tests
- **Baseline:** the numbers in Sprint 024's report (backend passed and skipped, Vitest, Playwright). State the delta.
- Run the `LineageEmitter` contract suite on the real adapter and the no-op adapter.
- Write one test per acceptance item and per threat-model row, using the names given there.
- Integration tests run as `gap_app` on the throwaway database with the outbox event bus. Kafka is not needed in pytest.
- No live verify script is needed: everything runs in process. Add no new skips.

## Notes from the Architect
- **Pins:** `openlineage-python==1.53.0`. Re-check it and record the result in `evidence/pins.txt`. Reuse the sqlglot pin from 024.
- **Boundaries:** `lineage/` imports only the kernel and `ports/`. It reads decision ids only through `EvidenceLookup`. Add its import-linter contract.
- **Redaction:**
  - Use a corpus of at least 20 SQL statements: strings, numbers, dates, IN lists and LIKE.
  - If a statement does not parse, store only its hash, with `sql_template` null. Never store the raw text.
- **Tenant:** the emitter takes the tenant from the job context. The consumer ignores any tenant-like field in the OpenLineage body. Test it with a forged body.
- **Milestone MA:** this sprint closes MA. Write `scripts/showcase/ma.sh` (`scripts/showcase/<milestone>.sh` in `planning/program/conventions.md`) and save its output in `evidence/ma-journey.txt`. Sprint 046 refreshes it.
- **Not linked:** an unresolved decision id is shown as "not linked". It is not an error.
- **Migration:** use the next free number after Sprint 024's head. It is forward only. Test the upgrade from 024's head.
- **Docs:** update ADR-0020, `docs/architecture.md`, `docs/contracts/lineage/`, `docs/operations.md`, `docs/design/IA.md` (if the nav changes), the OpenAPI snapshot, `.env.example`, CHANGELOG (with the test delta) and STATE.

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/025-lineage/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/025-lineage/evidence/pytest-int-e2e.xml   # expected count from tests/skip_allowlist.json
scripts/supply_chain/licence_gate.sh
scripts/ci/edition_smoke.sh
ENABLED_MODULES=gateway,data poetry run pytest -m edition_smoke -q   # Data edition with lineage off
poetry run python scripts/update_openapi.py
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Script names come from `planning/program/conventions.md`. Add `lineage` to the mypy file list. Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names, no model or tool attribution. Simple sentences in docs.

## Finish
Write `report.md` with:
- the acceptance table with evidence links
- the test numbers and the delta against Sprint 024
- the migration number
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(lineage): add lineage contract and agent facet schemas`
- `feat(db): add tenant lineage store tables`
- `feat(lineage): ingest openlineage events with redaction and evidence links`
- `test(lineage): cover redaction, tenant isolation and the reference graph`
- `feat(ui): add lineage graph page`
- `docs(adr): record lineage model and agent facets`
- `docs(planning): update state and changelog for lineage`

The Builder does not commit. A human runs the commands.

**Milestone MA (human actions, after QA signs off and the pull request merges):**
- Add a `CHANGELOG.md` section for `v0.25.0` with the test delta since `v0.15.0`, the migrations added in Sprints 016 to 025, new services and measured memory. The Builder drafts it in the report.
- Proposed tag, run by a human on `main`: `git tag -a v0.25.0 -m "MA Data plane"` then `git push origin v0.25.0`.

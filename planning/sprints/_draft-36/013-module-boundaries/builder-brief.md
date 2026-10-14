# Sprint 013: Builder brief
You are the Builder for Sprint 013 in /home/ubuntu/ai-platform, on branch `sprint/013-module-boundaries`. Infrastructure plus a small UI change, across all modules. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, `docs/architecture.md`, ADR-0005, ADR-0006, ADR-0012.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `planning/program/vision-and-architecture.md` (modules, editions, cross-module ports).
- `gateway/` (all), `ports/`, `adapters/registry.py`, `api/main.py`, `workers/`, `scripts/verify/receipt.py`, `ui/src/app/nav.ts`, `ui/src/app/shell.tsx`.
- `.claude/skills/governed-design/SKILL.md` before any UI code.

## Build
Order: ports and no-ops with contract suites; move the evidence core (pure move first, all tests green, then the sink); migration and record v2; registry, settings and the `module` stage; import-linter; UI; CI matrix; docs. Write a short plan in `build-log.md` first.

## Tests
- **Baseline:** the numbers in Sprint 012's report.
- The move must not change behaviour. Run the full suite after the pure move, before any new code, and save it as `evidence/after-move.txt`.
- Existing tests change only their import paths. Never change an expected value.
- Every acceptance item has a named test in the blueprint. Fakes: the no-op adapters are the fakes for the new ports.
- The migration test upgrades from the previous head with chained rows already in place.

## Notes from the Architect
- **Code facts:**
  - `gateway/record.py` writes the row, takes the chain link (`pg_advisory_xact_lock` per tenant) and publishes the decision event in the same transaction. Keep that order inside `PgDecisionSink`.
  - Importers of the moved files: `api/main.py`, `api/routers/receipts.py`, `workers/context.py`, `workers/handlers/purge.py`, and tests (`tests/trust_helpers.py`, `tests/unit/conftest.py`, `test_gateway_enforce.py`, `test_decision_event.py`, `test_retention.py`, `test_receipts.py` and others). `grep -rn "gateway\.\(record\|chain\|receipts\)"` finds them all.
  - `gateway/guardrails.py` imports `api.services.guardrails`. The gateway contract forbids importing `api`, so move that logic into `gateway/` and leave `api/services/guardrails.py` importing from it.
  - `workers/context.py` imports `api.agent.*` directly. The registry provides the agent-run handler instead.
  - The MCP endpoint is mounted with `app.mount(f"{API_PREFIX}/mcp/messages", ...)` and a raw `Route` for `/mcp/sse` in `api/main.py`. The deny handler must cover both.
  - `chain.canonical_json` already sorts keys with no spaces. Keep it as the one serialisation.
  - `scripts/verify/receipt.py` repeats the chain functions on purpose; `tests/e2e/test_receipts.py` keeps them in step. Update both.
  - Admin holds every `ActionKind` (`gateway/boundary.py`). A new stage does not change that.
- **Pins:** import-linter (UNV in `stack.md`): choose a release at least two weeks old and save it in `evidence/pins.txt`. Run the licence gate.
- **Migration:** the next free number after the previous sprint's head (0010 at the start of 011). Forward only. Never edit an older migration.
- **Decided:** the gateway package API is importable by every module (see blueprint). `/v1/system/modules` uses `kb:read` like `/v1/config`.
- **ADR-0013** covers module boundaries, cross-module ports and decision record v2.

## Run
```bash
poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
poetry run lint-imports
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/013-module-boundaries/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/013-module-boundaries/evidence/pytest-int-e2e.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python scripts/update_openapi.py
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Add `evidence` to the mypy file list (strict) and to the ruff line in CI and `AGENTS.md`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1 to A7, A-sec) with links to `evidence/`
- test numbers and the delta against Sprint 012's report
- the migration number taken
- deviations and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md`: contract (`ports/`, `api/models/`, `docs/api/openapi.json`, `feat(evidence)`), migration (`feat(db)`), code (`evidence/`, `gateway/`, `core/`, `adapters/`, `api/`, `workers/`, `feat(evidence)`), tests (`test(evidence)`), UI (`feat(ui)`), ops (`.github/`, `scripts/ci/edition_smoke.sh`, `pyproject.toml` import-linter section, `ci(ops)`), docs (`docs(adr)`), planning (`docs(planning)`), each with its `git add` paths, then the push and `gh pr create --base main` commands.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.

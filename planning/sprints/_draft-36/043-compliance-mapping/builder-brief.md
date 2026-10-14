# Sprint 043: Builder brief
You are the Builder for Sprint 043 in /home/ubuntu/ai-platform, on branch `sprint/043-compliance-mapping`. A vertical slice in module M2: contract first, then backend, then UI, then e2e. Work autonomously. Stop conditions are in AGENTS.md. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, `planning/QUESTIONS.md` (Q26).
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 042's `report.md` and `docs/contracts/evidence-pack.md`.
- Every earlier pack's `threat-model.md`: their tests are the OWASP evidence.
- `models.lock`, the guard stage (038), the oversight and incident logs (034, 039), `ai_systems` and the pack builder (042).
- `.claude/skills/governed-design/SKILL.md` before any UI code.

## Build
Everything in the blueprint. Order: contract, migration, generators, mapping files, coverage check, pack changes, UI, red-team script, date check, docs. Write mapping rows only for tests that exist. A control with no test is a gap row with an owner, not an invented test.

## Tests
- Baseline: the numbers in Sprint 042's report.
- Generators use golden files from the reference company. No network in pytest.
- The coverage check runs in CI after pytest, on the same JUnit file.
- Each acceptance item and each threat row has a named test.

## Notes from the Architect
- **Pins:** `garak==0.17.0` (Apache-2.0) and `pyrit==1.1.0` (MIT), from `stack.md`. Re-check each version, source and licence. Install them in a separate venv or container, never in the main Poetry lock: they pull torch and hosted-model SDKs. garak has no licence field on PyPI, so add it to `licence-exceptions.txt` (011) with its real licence and the source checked. Nothing else bypasses the gate. Pin the Strix CLI the same way. Save all three in `evidence/pins.txt`, and run them through `scripts/supply_chain/licence_gate.sh`. A tool with a non-OSI licence is not added: stop on that item and log it.
- **Spend:** the red team must use the fake model or local Ollama. If a tool needs a paid model key, that is a stop condition: mark A5 "not verified here" and go on. Strix may need a hosted model key to run; if it does, mark the Strix part "not verified here" with that reason, and keep the garak and PyRIT parts.
- **EUR-Lex:** fetch only from `eur-lex.europa.eu`, in the manual script. Never in pytest or default CI.
- **Q26 owners:** write an owner role for each number in `planning/DECISIONS.md` (for example "platform operator"). Do not change the numbers. They stay settings with defaults until their owner confirms them. If no owner can be named from the planning files, leave Q26 open with that note.
- **Wording:** "mapped to", "evidence for". Never "compliant", "certified" or "conformant".
- **Migration:** the next free number after Sprint 042's head. Forward only, tested from the previous head.

## Run
If Postgres, Valkey or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e scripts/compliance
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run python scripts/update_openapi.py
poetry run pytest -m unit -q --junitxml=planning/sprints/043-compliance-mapping/evidence/junit-unit.xml
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/043-compliance-mapping/evidence/junit.xml
poetry run python scripts/check_skips.py planning/sprints/043-compliance-mapping/evidence/junit.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python scripts/compliance/check_mappings.py --junit planning/sprints/043-compliance-mapping/evidence/junit-unit.xml --junit planning/sprints/043-compliance-mapping/evidence/junit.xml
scripts/redteam/release.sh
poetry run python scripts/compliance/check_eurlex.py
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names for the platform, no model or tool attribution.
- Short, simple sentences in docs and UI copy.

## Finish
Write `report.md` and `evidence/`. The report has: the acceptance table with evidence links, test numbers and the delta against Sprint 042, the migration number, the gap rows found, deviations, open questions, and proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, ops, docs, planning). No commits by the Builder. Update `planning/STATE.md` and `CHANGELOG.md`.

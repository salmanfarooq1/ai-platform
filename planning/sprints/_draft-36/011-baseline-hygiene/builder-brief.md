# Sprint 011: Builder brief
You are the Builder for Sprint 011 in /home/ubuntu/ai-platform, on branch `sprint/011-baseline-hygiene`. Infrastructure: planning files, settings, CI and supply chain. No API, schema or UI change. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- `planning/program/stack.md` (pins) and `planning/program/branching-and-commits.md` (scope list, commit blocks).
- `core/settings.py`, `scripts/docs/check_links.py`, `scripts/check_skips.py`, `.github/workflows/`, `docker-compose.yml`, `Dockerfile`.

## Build
Everything in the blueprint, in this order: planning drift, the two bugs, pins, skip allowlist, supply chain scripts, CI. Write a short plan in `build-log.md` first.

## Tests
- **Baseline:** 1568 backend passed, 10 skipped (live MinIO); 207 Vitest; 82 Playwright.
- Counts may only grow by the new tests. No skip is added.
- Add the four test files the blueprint names. Each acceptance item has a named test or command.
- No new service, so no live verify script.

## Notes from the Architect
- **Code facts:**
  - `_load_env_files` in `core/settings.py` uses `override=True` for `.env.local` only. `.env` already loads without override.
  - `scripts/docs/check_links.py` walks `root.rglob("*")` in `_known_names` and `doc_files`. Ask git for ignored paths once (`git ls-files --others --ignored --exclude-standard --directory`) and drop them. Outside a git checkout, skip nothing.
  - `scripts/check_skips.py` hard-codes `ALLOWED_CLASS` and `ALLOWED_REASON`. The JUnit class is `tests.contracts.test_object_store_contract`, the name holds `[minio`, the reason starts `live MinIO not available`.
  - CI installs Poetry with `pipx install poetry` (no pin) and caches `~/.cache/pypoetry`, not `.venv`. The secret scan uses `gitleaks/gitleaks-action@v2` with `GITHUB_TOKEN`.
  - The CI ruff line also covers `scripts/docs`.
  - `.gitleaksignore` holds two reviewed false positives (commit `8dc31ab`). Keep them.
  - The `ollama` compose service has no tag and no profile. Pin it here. Sprint 012 moves it to a profile.
- **Pins:** take them from `planning/program/stack.md`. Re-check each one and save tag, digest and source in `evidence/pins.txt`. Tool pins marked UNV (gitleaks, osv-scanner or grype) are chosen here and saved the same way.
- **Licence gate:** allow only OSI ids. Grafana is AGPL-3.0 (OSI) and runs only in an optional profile. LGPL and MPL are OSI. If a current dependency fails, do not widen the allowlist with a non-OSI id. Log it in `planning/QUESTIONS.md` and add it to `licence-exceptions.txt` only when the real licence is OSI.
- **Path filters** must never skip a required check silently. Use a filter job whose result the required jobs read, or keep required jobs unfiltered.
- **No migration** in this sprint.

## Run
```bash
poetry run ruff check api core gateway ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/011-baseline-hygiene/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/011-baseline-hygiene/evidence/pytest-int-e2e.xml   # expected count comes from tests/skip_allowlist.json
scripts/supply_chain/export_locks.sh --check
scripts/supply_chain/licence_gate.sh
scripts/supply_chain/licence_gate.sh --fixture tests/fixtures/licence/non_osi   # must fail
scripts/supply_chain/sbom.sh
gitleaks git --redact --no-banner .
cd ui && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
If Postgres or Redis is down: `docker compose up -d postgres redis` and `scripts/setup_db.sh`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs. Refer to them by env var name.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution in any file.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1 to A7, A-sec) with links to `evidence/`
- test numbers and the delta against the baseline
- "No migration"
- deviations from the blueprint, and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md`, for example: code (`core/settings.py`, `scripts/docs/`, `scripts/check_skips.py`, `fix(core)`), tests (`test(ci)`), ops (`.github/`, `docker-compose.yml`, `Dockerfile`, `scripts/supply_chain/`, `requirements/`, `ci(ops)`), docs (`docs(ops)`), planning (`planning/`, `CHANGELOG.md`, `docs(planning)`), each with its `git add` paths, then `git push -u origin sprint/011-baseline-hygiene` and `gh pr create --base main`.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.

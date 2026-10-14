# Sprint 045: Builder brief
You are the Builder for Sprint 045 in /home/ubuntu/ai-platform, on branch `sprint/045-packaging-editions`. Packaging across all modules. Work autonomously. Stop conditions are in AGENTS.md. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 044's `report.md`. Sprint 013's pack and ADR-0013 (modules, registry, edition smoke matrix). Sprint 011's supply chain scripts (`scripts/supply_chain/sbom.sh`, `scripts/supply_chain/licence_gate.sh`). Sprint 043's ML-BOM generator.
- `pyproject.toml`, `poetry.lock`, the `Dockerfile`, `docker-compose.yml`, `.github/workflows/`.

## Build
Everything in the blueprint. Order: entry points and registry discovery, wheel layout and build script, edition files and install script, Dockerfile build arg, SBOM and licence report, release workflow, runbooks and restore drill, docs. Keep the repo runnable from source as today: `poetry install` and `uvicorn api.main:app` must still work.

## Tests
- Baseline: the numbers in Sprint 044's report.
- The clean-machine install runs in a fresh container (`python:3.11-slim` by digest) with only `dist/` copied in.
- The restore drill uses a separate compose project name and new volumes. It never touches the main volumes.
- Each acceptance item and each threat row has a named test or a named step in a script.

## Notes from the Architect
- **Layout:** Poetry 2.3.3 builds one wheel per `pyproject.toml`. Pick a layout that keeps today's import paths (`gateway`, `core`, ...). Record it and the reason in `build-log.md` and the ADR-0013 section.
- **Shared packages:** two modules share a Python package today: the evidence core and the M2 extensions in `evidence/`, and the agent code in `api/agent/` and `api/mcp/` inside the kernel's `api`. Give each module its own importable package (a subpackage moved out, or a namespace package). No behaviour change; the full suite proves it.
- **One Alembic tree.** Do not split migrations per wheel. The kernel wheel ships them.
- **Entry point group** is `platform.modules`, as the seed says. It is only a string; no Python package is named `platform`.
- **Destructive actions:** the restore drill must never run `docker compose down -v` on the default project. A command that would is a stop condition.
- **Grafana** is AGPL-3.0, optional and unmodified. The licence report lists it as optional, not as a gate failure.
- **Migration:** none. Say so in the report.
- **Release tag:** this sprint adds the gate only. No tag here.

## Run
If Postgres, Valkey or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e scripts/release
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run python scripts/update_openapi.py
poetry run pytest -m unit -q --junitxml=planning/sprints/045-packaging-editions/evidence/junit-unit.xml
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/045-packaging-editions/evidence/junit.xml
poetry run python scripts/check_skips.py planning/sprints/045-packaging-editions/evidence/junit.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python scripts/compliance/check_mappings.py --junit planning/sprints/045-packaging-editions/evidence/junit-unit.xml --junit planning/sprints/045-packaging-editions/evidence/junit.xml
scripts/release/build_wheels.sh
for e in gateway assurance agents data full; do scripts/release/install_edition.sh "$e"; done
scripts/supply_chain/sbom.sh --release && poetry run python scripts/release/licence_report.py
scripts/verify/restore.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names for the platform, no model or tool attribution.
- Short, simple sentences in docs and runbooks.

## Finish
Write `report.md` and `evidence/`. The report has: the acceptance table with evidence links, test numbers and the delta against Sprint 044, "no migration", wheel sizes, measured memory per edition, deviations, open questions, and proposed commit blocks per `planning/program/branching-and-commits.md` (contract, code, tests, ops, docs, planning). No commits by the Builder. Update `planning/STATE.md` and `CHANGELOG.md`.

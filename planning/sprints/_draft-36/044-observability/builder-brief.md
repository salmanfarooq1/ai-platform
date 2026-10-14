# Sprint 044: Builder brief
You are the Builder for Sprint 044 in /home/ubuntu/ai-platform, on branch `sprint/044-observability`. Infrastructure plus one page, Kernel. This sprint closes milestone MD. Work autonomously. Stop conditions are in AGENTS.md. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 043's `report.md`. Sprint 008's pack for `/metrics` and the `observability` profile.
- `api/observability.py`, `docker-compose.yml` (profile `observability`), `docker/observability/`, `scripts/verify/observability.sh`.
- `.claude/skills/governed-design/SKILL.md` and the `dataviz` skill before the charts.

## Build
Everything in the blueprint. Order: settings and redaction, tracing in API and workers, gateway spans, GenAI opt-in, audit analytics port and adapter, routes, collector and dashboards, UI page, verify script, docs.

## Tests
- Baseline: the numbers in Sprint 043's report.
- pytest uses the in-memory span exporter. No collector is needed for pytest. The live run is `scripts/verify/observability.sh`.
- The canary test sends a fixed string through `/v1/agent/query`, a document upload and a data read, then scans every exported span and captured log line.
- Each acceptance item and each threat row has a named test.

## Notes from the Architect
- **Pins:** `otel/opentelemetry-collector-contrib:0.161.0` by digest. Pin the OpenTelemetry Python packages and the semantic conventions package exactly. Prometheus and Grafana keep the Sprint 011 pins. Save them in `evidence/pins.txt`.
- **Opt-in value:** use the value the pinned semantic conventions document for GenAI (for example `gen_ai_latest_experimental`). Record the version in `/v1/observability/status`.
- **DuckDB placement:** DuckDB is imported only in `adapters/` (and `dataplane/`). The kernel uses the port. The adapter never attaches Postgres.
- **Never block a request on telemetry.** Batch exporters only. A down collector loses spans, not calls.
- **Grafana password:** removing the `admin` default changes local setup. Update `.env.example`, `docs/getting-started.md` and the verify script together.
- **Migration:** none expected. If one is needed, the next free number after Sprint 043's head.
- **Milestone MD:** A8 runs the MD journey on the reference company. Use `scripts/showcase/md.sh` if an earlier sprint wrote it; otherwise run the steps by hand from `docs/showcase.md` and save the output. Sprint 046 owns the final script.

## Run
If Postgres, Valkey or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run python scripts/update_openapi.py
poetry run pytest -m unit -q --junitxml=planning/sprints/044-observability/evidence/junit-unit.xml
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/044-observability/evidence/junit.xml
poetry run python scripts/check_skips.py planning/sprints/044-observability/evidence/junit.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python scripts/compliance/check_mappings.py --junit planning/sprints/044-observability/evidence/junit-unit.xml --junit planning/sprints/044-observability/evidence/junit.xml
docker compose --profile observability config >/dev/null
scripts/verify/observability.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names for the platform, no model or tool attribution.
- Short, simple sentences in docs and UI copy.

## Finish
Write `report.md` and `evidence/`. The report has: the acceptance table with evidence links, test numbers and the delta against Sprint 043, migrations (or "none"), deviations, open questions, measured memory, and proposed commit blocks per `planning/program/branching-and-commits.md` (contract, code, tests, UI, ops, docs, planning). No commits by the Builder. Update `planning/STATE.md` and `CHANGELOG.md`.

**Milestone MD (human actions, after QA signs off and the pull request merges):**
- Add a `CHANGELOG.md` section for `v0.44.0` with the test delta since `v0.39.0`, the migrations added in Sprints 040 to 044, new services (timestamp authority, OTel collector) and measured memory. The Builder drafts it in the report.
- Proposed tag, run by a human on `main`: `git tag -a v0.44.0 -m "MD Assurance"` then `git push origin v0.44.0`.

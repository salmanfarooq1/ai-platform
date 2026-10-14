# Sprint 029: Builder brief
You are the Builder for Sprint 029 in `/home/ubuntu/ai-platform`, on branch `sprint/029-reports-alerts`. This is a vertical slice: contract, backend, UI and an e2e test. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md` and `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md` and `threat-model.md`.
- The reports of Sprints 017 (snapshot event), 018 (scheduler, egress), 025 (lineage facets) and 028 (render path).
- `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
1. Contract, tables, job kinds and schedules.
2. Report run with the manifest, then PDF and CSV export, then delivery adapters.
3. Alerts, then lineage and events.
4. UI: Reports page, Subscribe and Alert me actions, Inbox.

## Tests
- **Baseline:** the numbers in Sprint 028's report. State the delta.
- One test per acceptance item and per threat-model row, using the names given there.
- Run PDF tests with the network guard on.
- Live verify: `scripts/verify/mail.sh` with the `mail` profile. Add no new skips.

## Notes from the Architect
- **Pins:** `vl-convert-python==1.9.0.post1` and `weasyprint==70.0` (both BSD-3). vl-convert 1.9.0 bundles Vega-Lite 6.4.1 and Vega 6.2.0, the same as the UI pins (028). Pass `vl_version="6.4"` and add a golden test that tile SVG matches the UI output. WeasyPrint needs Pango in the worker image; record the image size change.
- **No author rights,** as in 028. A run always carries the recipient's principal.
- **Link, not data,** for email by default.
- **Boundaries:** `insights/` imports only the kernel and `ports/`. Use the kernel object store's presign method and the 018 scheduler. Write the small hysteresis in `insights/alerts.py`. Reuse render from 028.
- **Inbox is kernel:** `core/inbox.py`, not `insights/`.
- **Placeholders:** retention, dedupe window and the attachment setting. Log one question each.
- **Migration:** next free number after Sprint 028's head.
- **Docs:** ADR-0031, `docs/architecture.md`, `docs/operations.md`, `docs/configuration.md`, the API docs, `.env.example`, the OpenAPI snapshot, CHANGELOG (with the test delta), STATE and DECISIONS.

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/029-reports-alerts/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/029-reports-alerts/evidence/pytest-int-e2e.xml   # expected count from tests/skip_allowlist.json
scripts/supply_chain/licence_gate.sh
scripts/ci/edition_smoke.sh
scripts/verify/mail.sh
poetry run python scripts/update_openapi.py
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Script names come from `planning/program/conventions.md`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names, no model or tool attribution. Use simple sentences in docs.

## Finish
Write `report.md` with:
- the acceptance table with evidence links
- the test numbers and the delta against Sprint 028
- the migration number and the image size change
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(insights): add subscriptions, alerts and report run contract`
- `feat(insights): render reports per recipient with manifests and offline pdf`
- `feat(insights): deliver reports to the inbox and an optional smtp adapter`
- `feat(ui): add reports page, subscribe and alert actions, and inbox`
- `test(insights): add recipient rights, csv and alert tests`
- `docs(planning): update state, decisions and changelog for reports and alerts`

The Builder does not commit. A human runs the commands.

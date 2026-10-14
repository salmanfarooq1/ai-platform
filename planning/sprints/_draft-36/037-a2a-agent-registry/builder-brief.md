# Sprint 037: Builder brief
You are the Builder for Sprint 037 in /home/ubuntu/ai-platform, on branch `sprint/037-a2a-agent-registry`. This is a vertical slice with one spike. Work autonomously. Stop conditions are in `AGENTS.md`: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- The Sprint 033 pack, `api/mcp/` and the registry code (the pattern to copy). The Sprint 027 taint rules. The Sprint 036 delegation chain.

## Build
Write `build-log.md` with a short plan first.
1. Pin check: `a2a-sdk==1.1.5`; confirm it implements A2A v1.0 and its card signature format. Save in `evidence/pins.txt`.
2. Contract: `/v1/a2a`, the card routes, the `a2a_agent` kind on the Sprint 033 registry routes. Refresh OpenAPI.
3. Port, adapter, settings, import lint entry.
4. Migration: new columns on `mcp_registry_entries`, `a2a_tasks`.
5. Gateway: `a2a.call`, the `peer` stage (after `boundary`, before `policy`), reason codes, the record v2 `a2a` extension.
6. UI: Governance > Agent registry.
7. The agentgateway spike on `spike/037-agentgateway`, last.

## Tests
- Baseline: the numbers in Sprint 036's report. State the delta.
- Peers: in-process, through the ASGI app. No real network.
- Every test named in `threat-model.md`, and one named test per acceptance item.

## Notes from the Architect
- **Code fact.** The MCP SDK is imported in `api/mcp/` and `api/middleware/auth.py` today. Keep `a2a-sdk` to `api/a2a/` and `adapters/`, and add it to `tests/unit/test_import_lint_ports.py` and the import-linter contracts.
- **Routes.** Every product route is under `/v1`. Rule 9 in `planning/program/vision-and-architecture.md` allows public discovery documents under `/.well-known/`; Sprint 032 recorded it and Sprint 033 used it. Serve the platform card at `/.well-known/agent-card.json` and at `/v1/a2a/agent-card.json`, and add the path to the list in `docs/architecture.md`.
- **Registry names.** Use Sprint 033's table `mcp_registry_entries` and its routes under `/v1/mcp/registry/servers`. Do not add a second registry table or prefix.
- **Canonical form.** Sign and hash the card in JCS form without its `signatures` member. The digest on decisions is SHA-256 of that form.
- **Taint.** An A2A message is untrusted content. Feed it through the same taint path as a document.
- **Spike.** Write the result whether it passes or fails. Do not add agentgateway to `pyproject.toml`, compose or CI.
- **Migration number:** the next free number after Sprint 036's head.

## Run
If the local stack is down: `docker compose up -d postgres valkey` (service names as of Sprint 012). Then run every line below and save the output in `evidence/`.
- `poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`, then `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/037-a2a-agent-registry/evidence/junit.xml`
- `poetry run python scripts/check_skips.py planning/sprints/037-a2a-agent-registry/evidence/junit.xml` (the expected count comes from `tests/skip_allowlist.json`, Sprint 011)
- `scripts/supply_chain/licence_gate.sh` (the licence gate from Sprint 011)
- `scripts/ci/edition_smoke.sh` (all five editions, Sprint 013; CI runs it from `.github/workflows/editions.yml`)
- `opa test policy/ -v` (the pinned `opa` binary and the Rego bundle from Sprint 031)
- `poetry run python scripts/update_openapi.py` after any contract change, then the OpenAPI drift test.
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green. Say whether the code or the expectation was wrong.
- No secrets in files or logs. Refer to them by env var name.
- No commits or pushes. No "demo" wording. No brand names. No model or tool attribution in any file.
- Plain words and simple sentences in docs.

## Finish
- Every acceptance check has captured output in `evidence/`, under the file name `acceptance.md` gives.
- Update docs in lockstep: the ADR, `docs/`, `.env.example`, the OpenAPI snapshot, `planning/STATE.md`, `CHANGELOG.md` (test delta, migration, measured memory if any).
- Write `report.md`:
  - the acceptance table (check, result, evidence file)
  - test numbers against the baseline
  - deviations from the blueprint, and why
  - open questions (also in `planning/QUESTIONS.md`)
  - proposed commit blocks, in the order of `planning/program/branching-and-commits.md`, each with its `git add` paths and message
- Do not run `git commit` or `git push`. A human runs the blocks.
- Suggested blocks: `feat(protocols)` port and contract; `feat(db)` migration; `feat(protocols)` A2A server, cards and gateway stage; `test(protocols)`; `feat(ui)`; `docs(adr)` ADR-0026; `docs(planning)` with the spike result.

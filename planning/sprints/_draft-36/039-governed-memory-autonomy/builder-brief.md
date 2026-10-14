# Sprint 039: Builder brief
You are the Builder for Sprint 039 in /home/ubuntu/ai-platform, on branch `sprint/039-governed-memory-autonomy`. This is a vertical slice: contract, migration, gateway, worker job, UI, e2e. Work autonomously. Stop conditions are in `AGENTS.md`: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- The Sprint 027 taint code, the Sprint 034 approvals and oversight log, the Sprint 038 guard stages, the Sprint 008 cost stage and eval gate (`scripts/eval/run_gate.py`), `workers/` (job kinds and the scheduler).

## Build
Write `build-log.md` with a short plan first.
1. Contract: memory, autonomy and incident routes. Refresh OpenAPI.
2. Migration: `agent_memory`, `agent_autonomy`, `agent_autonomy_changes`, `incidents`, `incident_events`.
3. Gateway: action kinds, trust tier rules, recall filter, policy fields in both engines, reason codes, record v2 `memory` extension.
4. Agent tools: `remember` and `recall` call the memory actions. No other path writes memory.
5. Worker: `autonomy_review` job and the memory expiry purge, both idempotent per tenant and window.
6. UI: Governance > Agent memory, Evidence > Incidents.

## Tests
- Baseline: the numbers in Sprint 038's report. State the delta.
- Fakes: `tests/fake_guard.py` decides which writes are poisoned; the fake LLM; a fake eval result for regressions.
- Every test named in `threat-model.md`, and one named test per acceptance item.

## Notes from the Architect
- **Strict rule 10.** Decision records hold hashes and ids. Memory `content` lives only in `agent_memory`, under RLS.
- **Tier source.** The gateway sets the tier from the source and the run's taint (`EnforcementContext.taint`, Sprint 027). Never take a tier from the agent's request.
- **PolicyInput.** Add the autonomy `tier` to `PolicyInput` (031), with decision-table rows for both engines.
- **Names.** The route is singular: `/v1/agent/{agent_id}/autonomy`. The event is `platform.agents.autonomy.changed.v1`.
- **Signed change.** "Signed" means the change is a chained decision with a receipt. Do not add a second signing key.
- **Art. 73 deadlines** are settings (`INCIDENT_REPORT_DAYS`, one per incident class). Give them placeholder defaults marked for the Sprint 043 check, and log a question. Do not hard-code legal day counts.
- **Thresholds** for tightening are placeholders until an owner confirms them: settings with defaults and a question in `planning/QUESTIONS.md`. Never present them as agreed rules.
- **Milestone MC:** this sprint closes MC. A7 runs the MC journey with `scripts/showcase/mc.sh` (started in Sprint 034). Extend it with the steps from Sprints 035 to 039. Sprint 046 refreshes it.
- **Migration number:** the next free number after Sprint 038's head.

## Run
If the local stack is down: `docker compose up -d postgres valkey` (service names as of Sprint 012). Then run every line below and save the output in `evidence/`.
- `poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`, then `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/039-governed-memory-autonomy/evidence/junit.xml`
- `poetry run python scripts/check_skips.py planning/sprints/039-governed-memory-autonomy/evidence/junit.xml` (the expected count comes from `tests/skip_allowlist.json`, Sprint 011)
- `scripts/supply_chain/licence_gate.sh` (the licence gate from Sprint 011)
- `scripts/ci/edition_smoke.sh` (all five editions, Sprint 013; CI runs it from `.github/workflows/editions.yml`)
- `opa test policy/ -v` (the pinned `opa` binary and the Rego bundle from Sprint 031)
- `poetry run python scripts/update_openapi.py` after any contract change, then the OpenAPI drift test.
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e`. Never run `playwright install`.
- Showcase: `scripts/showcase/mc.sh` (the full MC journey).

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
- Suggested blocks: `feat(memory)` contract; `feat(db)` migration; `feat(memory)` gateway, tools and worker job; `test(memory)`; `feat(ui)`; `docs(adr)` ADR-0028; `docs(planning)`.

**Milestone MC (human actions, after QA signs off and the pull request merges):**
- Add a `CHANGELOG.md` section for `v0.39.0` with the test delta since `v0.30.0`, the migrations added in Sprints 031 to 039, new services (OPA, Keycloak, guard service) and measured memory. The Builder drafts it in the report.
- Proposed tag, run by a human on `main`: `git tag -a v0.39.0 -m "MC Governance depth"` then `git push origin v0.39.0`.

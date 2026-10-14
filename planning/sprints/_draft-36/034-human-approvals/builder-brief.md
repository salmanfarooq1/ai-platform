# Sprint 034: Builder brief
You are the Builder for Sprint 034 in /home/ubuntu/ai-platform, on branch `sprint/034-human-approvals`. This is a vertical slice: contract, then migration, then gateway and routes, then UI, then e2e. Work autonomously. Stop conditions are in `AGENTS.md`: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- The Sprint 023 pack and code (the approval model), the Sprint 029 kernel inbox (`core/inbox.py`), the Sprint 026 guard, the Sprint 031 three outcomes, the Sprint 032 AuthZEN API, the Sprint 033 MCP transport.
- `gateway/enforce.py`, `gateway/reasons.py`, `api/agent/router.py`, `core/identity/run_tokens.py`, `docs/adr/0009-agent-runtime.md`.

## Build
Everything in the blueprint. Write `build-log.md` with a short plan first.
1. Contract: the `approvals:decide` scope, the `runtime_action` kind on the shared approvals model, stop and override models, the `Approval-Id` header. Refresh OpenAPI.
2. Migration: `action_approvals`, `oversight_events`, the wider `approvals.kind` CHECK, `jobs.output_withheld`.
3. Gateway: `gateway/approvals.py`, the approval check in the policy stage's `approval_required` branch, reason codes, action kinds, the record v2 `approval` extension.
4. Routes: approval queue, approver view, approve, reject, stop, override. MCP elicitation. AuthZEN `context.approval`.
5. UI: the Approvals tabs and the run buttons.
6. Switch the Sprint 026 over-limit deny to approval required, and wire the salary journey into the showcase script.

## Tests
- Baseline: the numbers in Sprint 033's report. State the delta.
- Fakes: the fake LLM, the in-process MCP client from Sprint 033, the fake sandbox for stop.
- Every test named in `threat-model.md`, and one named test per acceptance item.
- No new skips. Anything that needs a live service goes in a verify script, not a skipped test.

## Notes from the Architect
- **Code fact.** The runtime port already stops a run (`AgentRuntime.stop`, also during a tool call; ADR-0009). The route only calls it, then revokes run tokens with `revoke_run_tokens`.
- **Code fact.** `enforce()` runs `STAGES` in order and the first deny wins. Sprint 031 makes the policy stage return a deny for `approval_required`. Change only that branch to call the approval check, so guardrails, rate, budget and cost still run after an approval.
- **Hash input.** Build the canonical action from system values only: the normalised SQL or the tool arguments, typed parameters, snapshot id, principal id, purpose, policy bundle hash. Use the evidence core's canonical JSON. Never hash agent prose.
- **Single use.** The consume and the expiry check are one SQL statement. Do not read then write.
- **Separation of duties.** Use the Sprint 023 check. Do not write a second one. Extend the `duties` stage to `approval.decide`. Reuse the 023 codes `separation_of_duties` and `step_already_decided`; there is no `approval_self` or `approval_closed`.
- **Inbox is kernel.** Post `approval_pending` items through `core/inbox.py` (Sprint 029). The Approvals list is the "approval queue", not an inbox.
- **Surfaces.** For `surface` in `dashboard`, `report`, `alert`, an `approval_required` verdict becomes tile `withheld` with no approval rows.
- **One approvals model.** Extend the shared `/v1/approvals` route and model from Sprint 023 with `kind = runtime_action`. Do not add a second router or prefix. If the 023 code differs from `planning/program/conventions.md`, follow conventions and record it there.
- **Scope.** `approvals:decide` is new here. Access requests keep `data:steward` (Sprint 021).
- **Evidence text.** Normalised SQL lives only in `action_approvals.evidence`. Decision records and events hold the hash.
- **AuthZEN and MCP profiles** are drafts. Label them "draft-compatible" in docs and OpenAPI descriptions.
- **Migration number:** the next free number after Sprint 033's head. Upgrade is tested from that head.

## Run
If the local stack is down: `docker compose up -d postgres valkey` (service names as of Sprint 012). Then run every line below and save the output in `evidence/`.
- `poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`, then `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/034-human-approvals/evidence/junit.xml`
- `poetry run python scripts/check_skips.py planning/sprints/034-human-approvals/evidence/junit.xml` (the expected count comes from `tests/skip_allowlist.json`, Sprint 011)
- `scripts/supply_chain/licence_gate.sh` (the licence gate from Sprint 011)
- `scripts/ci/edition_smoke.sh` (all five editions, Sprint 013; CI runs it from `.github/workflows/editions.yml`)
- `opa test policy/ -v` (the pinned `opa` binary and the Rego bundle from Sprint 031)
- `poetry run python scripts/update_openapi.py` after any contract change, then the OpenAPI drift test.
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e`. Never run `playwright install`.
- Showcase: `scripts/showcase/mc.sh salary`. If no earlier sprint wrote `mc.sh`, start it here with the salary step. Sprint 039 runs the full MC journey and Sprint 046 refreshes it.

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
- Suggested blocks: `feat(approvals)` contract; `feat(db)` migration; `feat(approvals)` gateway and routes; `test(approvals)`; `feat(ui)`; `chore(ops)` showcase script; `docs(adr)` ADR-0024 and docs; `docs(planning)`.

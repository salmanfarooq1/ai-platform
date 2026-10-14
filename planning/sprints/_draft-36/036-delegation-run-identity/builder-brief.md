# Sprint 036: Builder brief
You are the Builder for Sprint 036 in /home/ubuntu/ai-platform, on branch `sprint/036-delegation-run-identity`. This is a vertical slice that starts with a spike. Work autonomously. Stop conditions are in `AGENTS.md`: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `core/identity/run_tokens.py`, `api/middleware/auth.py`, `api/routers/sandbox.py`, `docs/adr/0009-agent-runtime.md`, the Sprint 035 OIDC code.

## Build
Write `build-log.md` with a short plan first.
1. The spike, on `spike/036-token-exchange`. Record the result before writing the adapter.
2. Contract: the delegate route, the run view fields. Refresh OpenAPI.
3. Port, platform adapter (and the Keycloak adapter only if the spike passed), registry, settings.
4. Migration: `delegation_tokens`.
5. Rules in `core/identity/delegation.py`; the `delegation.exchange` action; reason codes; the record v2 `delegation` extension.
6. UI: the chain panel.

## Tests
- Baseline: the numbers in Sprint 035's report. State the delta.
- Fakes: the fake OIDC issuer from Sprint 035 for subject tokens with `may_act`; the fake sandbox for runs.
- Every test named in `threat-model.md`, and one named test per acceptance item.

## Notes from the Architect
- **Code fact.** Run tokens (`grt_...`) are opaque, hashed, bound to one `execution_id`, capped at 3600 s, and valid only on `/v1/sandbox/runs/{execution_id}/...`. Keep them. The delegation token is a second, audience-bound credential the run asks for.
- **Code fact.** `EnforcementContext.execution_id` already reaches every run decision. Add the chain beside it, and write it through the record v2 extension, never as a new hashed column.
- **Narrowing** is strict rule 5. A request equal to the caller's scopes is allowed; one scope more is refused.
- **The spike may fail.** That is a result, not a stop. The platform adapter is then the only one, and ADR-0025 says so.
- **Preview feature.** Keycloak delegation (`actor_token`, nested `act`) needs `--features=token-exchange-delegation`, a preview feature. Turn it on in the throwaway spike profile only, never in `identity`. Decided 2026-10-11: the platform-minted adapter is the default. Preview features never run in the default stack.
- **Report runs.** Model 029 report and alert runs as delegations: `sub=recipient`, `act=job:insights.report.run`, `may_act` naming `insights.report`.
- **PolicyInput.** Add the delegation chain (no token text) and decision-table rows for both engines.
- **SPIRE** is documented only. Do not add `spiffe` to dependencies unless a test needs to parse ids with it; plain string handling is enough.
- **Keys.** `DELEGATION_SIGNING_KEY_FILE` is a new key, separate from the receipt key. Local mode may generate one at startup and log only its key id, as receipts do.
- **Migration number:** the next free number after Sprint 035's head.

## Run
If the local stack is down: `docker compose up -d postgres valkey` (service names as of Sprint 012). Then run every line below and save the output in `evidence/`.
- `poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`, then `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/036-delegation-run-identity/evidence/junit.xml`
- `poetry run python scripts/check_skips.py planning/sprints/036-delegation-run-identity/evidence/junit.xml` (the expected count comes from `tests/skip_allowlist.json`, Sprint 011)
- `scripts/supply_chain/licence_gate.sh` (the licence gate from Sprint 011)
- `scripts/ci/edition_smoke.sh` (all five editions, Sprint 013; CI runs it from `.github/workflows/editions.yml`)
- `opa test policy/ -v` (the pinned `opa` binary and the Rego bundle from Sprint 031)
- `poetry run python scripts/update_openapi.py` after any contract change, then the OpenAPI drift test.
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e`. Never run `playwright install`.
- `scripts/verify/keycloak.sh` again, to show the exchange path (if built) on a live provider, or record "not verified here".

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
- Suggested blocks: `feat(identity)` port and contract; `feat(db)` migration; `feat(identity)` adapters, rules and gateway extension; `test(identity)`; `feat(ui)`; `docs(adr)` ADR-0025; `docs(planning)` with the spike result.

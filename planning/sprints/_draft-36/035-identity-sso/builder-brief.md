# Sprint 035: Builder brief
You are the Builder for Sprint 035 in /home/ubuntu/ai-platform, on branch `sprint/035-identity-sso`. This is a vertical slice: contract, migration, identity code, compose, UI, e2e. Work autonomously. Stop conditions are in `AGENTS.md`: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `docs/adr/0007-web-edge-session.md`, `api/web_edge/`, `api/middleware/auth.py`, `core/identity/jwt.py`, `core/identity/store.py`, `planning/program/reference-data-portal.md` ("What we avoid").

## Build
Everything in the blueprint. Write `build-log.md` with a short plan first.
1. Contract: the two OIDC routes, `GET /v1/identity/provider`, error codes. Refresh OpenAPI.
2. Migration: `external_identities` and `auth_lookup_external`.
3. `core/identity/oidc.py`, the mapping file loader, settings, middleware paths, session creation.
4. Compose profile `identity`, the realm export, `scripts/verify/keycloak.sh`, the nightly CI job.
5. UI: sign-in button, Platform > Identity, error pages.
6. The fake issuer, the anti-pattern tests and `scripts/verify/mutate_identity.py`.

## Tests
- Baseline: the numbers in Sprint 034's report. State the delta.
- Fake: `tests/fake_oidc.py`. The network guard fixture stays on; the fake is served through the HTTP client's transport, not a socket.
- Live: `scripts/verify/keycloak.sh` (nightly), not a skipped pytest.
- The reference company personas get groups in the realm export that match their Sprint 015 policy files. Add `bi-authors` (`data:read`, `insights:write`) with a persona test.

## Notes from the Architect
- **Code fact.** `JwtVerifier` today needs `sub` to be the principal UUID and allows HS256 when `JWT_SECRET` is set. Do not change that path. Add the OIDC path beside it, keyed by issuer. Log the HS256 question in `planning/QUESTIONS.md`.
- **Code fact.** A cookie session re-checks its sign-in key on every request (`auth_lookup_key`). An OIDC session has no key. Re-check the principal and the `external_identities` link instead, and end the session when either is gone.
- **Code fact.** `parse_scopes` already drops unknown scopes. Keep that, and also refuse unknown scopes in the mapping file at startup.
- **Pins.** Keycloak `26.7.4` by digest. Re-check the tag and save it in `evidence/pins.txt`.
- **Secrets.** The client secret and the admin password come from files. Never print them, not even in the verify script.
- **Report principals (029).** A report or alert run acts as the recipient. Store `last_scopes` and `last_seen_at` on each sign-in. `IDENTITY_STALE_DAYS` is a placeholder default; log a question for it.
- **Migration number:** the next free number after Sprint 034's head.

## Run
If the local stack is down: `docker compose up -d postgres valkey` (service names as of Sprint 012). Then run every line below and save the output in `evidence/`.
- `poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`, then `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/035-identity-sso/evidence/junit.xml`
- `poetry run python scripts/check_skips.py planning/sprints/035-identity-sso/evidence/junit.xml` (the expected count comes from `tests/skip_allowlist.json`, Sprint 011)
- `scripts/supply_chain/licence_gate.sh` (the licence gate from Sprint 011)
- `scripts/ci/edition_smoke.sh` (all five editions, Sprint 013; CI runs it from `.github/workflows/editions.yml`)
- `opa test policy/ -v` (the pinned `opa` binary and the Rego bundle from Sprint 031)
- `poetry run python scripts/update_openapi.py` after any contract change, then the OpenAPI drift test.
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e`. Never run `playwright install`.
- `docker compose --profile identity config` and `scripts/verify/keycloak.sh` (or record "not verified here" with the reason).
- `poetry run python scripts/verify/mutate_identity.py`

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
- Suggested blocks: `feat(identity)` contract; `feat(db)` migration; `feat(identity)` OIDC code and settings; `test(identity)`; `feat(ui)`; `chore(ops)` compose, realm export, verify scripts, nightly job; `docs(identity)`; `docs(planning)`.

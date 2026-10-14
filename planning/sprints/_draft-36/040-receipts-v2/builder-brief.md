# Sprint 040: Builder brief
You are the Builder for Sprint 040 in /home/ubuntu/ai-platform, on branch `sprint/040-receipts-v2`. This is infra with a small UI change. Work autonomously. Stop conditions are in `AGENTS.md`: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `docs/adr/0012-receipts-and-hash-chain.md`, the evidence core (`evidence/`, moved from `gateway/receipts.py` and `gateway/chain.py` in Sprint 013), `scripts/verify/receipt.py`, the Sprint 013 record v2 rules, the Sprint 031 bundle hash and `GET /v1/decisions/{id}/policy-input`, Sprint 032's `POST /v1/decisions/{id}/replay` and `scripts/verify/replay_decision.py`, `planning/QUESTIONS.md` Q28 and Q31.

## Build
Write `build-log.md` with a short plan first.
1. Pin check: `cbor2==6.1.5` (or `cwt==3.3.0`), `python-pkcs11` (pin it, check its licence). Save in `evidence/pins.txt`.
2. `ports/signer.py`, the file and PKCS#11 adapters, the contract suite, registry and settings.
3. COSE receipt build and verify in the evidence core. Keep the v1 code path.
4. Revocation file, keys route fields, the attestation extension.
5. Offline verifier v2 and the parity test.
6. Runbook section and `scripts/verify/key_drill.sh`. CI step for `softhsm2`.
7. UI: Evidence > Receipts.

## Tests
- Baseline: the numbers in Sprint 039's report. State the delta.
- SoftHSM runs in CI. On a machine without it, the PKCS#11 case is in the skip allowlist with that reason; the file adapter always runs.
- Every test named in `threat-model.md`, and one named test per acceptance item.

## Notes from the Architect
- **Code fact.** `Keyring` already keeps previous public keys (`RECEIPT_PREVIOUS_PUBLIC_KEYS`) and `key_id` is the first 16 hex of the SHA-256 of the raw public key. Keep both rules for v2.
- **Code fact.** `scripts/verify/receipt.py` imports nothing from the platform, and a test keeps it in step with the chain code. Keep it standalone. `cbor2` is its only new import.
- **Same bytes.** The COSE payload is exactly the canonical text the chain hashes. Do not create a second canonical form.
- **Q28** has the Architect's proposal in `requirements.md` (no back-fill). Build it, write it in ADR-0029 as a proposal, and add it to Q28 in `planning/QUESTIONS.md` for the owner to confirm. Do not close Q28.
- **TSA and log keys** get their slots and settings now. Nothing signs with them until Sprint 041.
- **No migration expected.** If one is needed, use the next free number after Sprint 039's head.

## Run
If the local stack is down: `docker compose up -d postgres valkey` (service names as of Sprint 012). Then run every line below and save the output in `evidence/`.
- `poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`, then `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/040-receipts-v2/evidence/junit.xml`
- `poetry run python scripts/check_skips.py planning/sprints/040-receipts-v2/evidence/junit.xml` (the expected count comes from `tests/skip_allowlist.json`, Sprint 011)
- `scripts/supply_chain/licence_gate.sh` (the licence gate from Sprint 011)
- `scripts/ci/edition_smoke.sh` (all five editions, Sprint 013; CI runs it from `.github/workflows/editions.yml`)
- `opa test policy/ -v` (the pinned `opa` binary and the Rego bundle from Sprint 031)
- `poetry run python scripts/update_openapi.py` after any contract change, then the OpenAPI drift test.
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e`. Never run `playwright install`.
- `scripts/verify/key_drill.sh`
- `python3 scripts/verify/receipt.py receipt evidence/sample-v2.json --keys evidence/keys.json --require-v2`

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
- Suggested blocks: `feat(receipts)` port and contract; `feat(receipts)` COSE receipts, signers, revocation and verifier; `test(receipts)`; `feat(ui)`; `ci(receipts)` SoftHSM step and drill script; `docs(adr)` ADR-0029; `docs(planning)` with Q31 closed and the Q28 proposal logged.

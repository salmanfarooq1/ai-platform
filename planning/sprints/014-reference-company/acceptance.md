# Sprint 014: Acceptance

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

- [x] **A1. Personas.** Six personas use only implemented scopes and refer to tenant-wide journey policies. Setup reuses the verified fixture-owned tenant and does not create one. Evidence: `evidence/accept-live-m0.log` (PASS personas), `tests/integration/refco/test_identity_key_listing.py`.
- [x] **A2. Private keys.** Keys are written atomically to `.showcase/keys.env` with mode 0600 in a private directory. Reruns reuse valid keys and rotate missing, revoked or mismatched keys, revoking only the prefix setup issued; other keys stay untouched. Sentinel checks find no full key in output, logs, traces or artifacts. Evidence: `evidence/accept-refco.log` (rotation keeps foreign keys, revokes only the issued prefix), `evidence/accept-live-m0.log`.
- [x] **A3. M0 journey.** The local script denies search before inference, and the Ollama request count does not change. The auditor verifies the receipt offline. The Gateway-only process shows agents off, records the disabled-agent response and serves Modules to a scoped credential. The baseline policy is restored as a new version without overwriting concurrent changes. Evidence: `evidence/accept-live-m0.log` (real Ollama, throwaway database), `tests/integration/refco/test_policy_cas.py`.
- [x] **A4. Playwright.** The isolated M0 project verifies the deny, receipt and Modules state. Evidence: `evidence/accept-playwright.log`.
- [x] **A-sec.** Threat-model tests pass. Evidence: `evidence/accept-unit.log`, `evidence/accept-refco.log`, `tests/unit/refco/test_public_seams.py`.


Closed 2026-11-16 by the Architect: `accept.sh` 8/8 PASS, summary in `evidence/checks.txt`. Product diff vs 013 passed the second-client check (identity inventory reads, `inspect_credential`, policy compare-and-swap, `OLLAMA_BASE_URL`).

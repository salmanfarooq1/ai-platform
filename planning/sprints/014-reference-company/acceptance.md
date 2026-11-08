# Sprint 014: Acceptance

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

- [ ] **A1. Personas.** Six personas use only implemented scopes and refer to tenant-wide journey policies. Setup reuses the verified fixture-owned tenant and does not create one. Evidence: `evidence/personas.txt`.
- [ ] **A2. Private keys.** Keys are written atomically to `.showcase/keys.env` with mode 0600 in a private directory. Reruns reuse valid keys and stop on missing, revoked or mismatched keys. Sentinel checks find no full key in output, logs, traces or artifacts. Evidence: `evidence/personas.txt`.
- [ ] **A3. M0 journey.** The local script denies search before inference, and the Ollama request count does not change. The auditor verifies the receipt offline. The Gateway-only process shows agents off, records the disabled-agent response and serves Modules to a scoped credential. The baseline policy is restored as a new version without overwriting concurrent changes. Evidence: `evidence/m0.txt`.
- [ ] **A4. Playwright.** The isolated M0 project verifies the deny, receipt and Modules state. Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** Threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

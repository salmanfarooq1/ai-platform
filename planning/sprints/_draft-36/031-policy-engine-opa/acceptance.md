# Sprint 031: Acceptance
- [ ] **A1.** All checks pass, including `opa test policy/`. The test delta is stated against Sprint 030's report. `check_skips` passes with the allowlist, with no new entries. Evidence: `evidence/checks.txt`.
- [ ] **A2.** The Python engine and OPA give the same outcome and reason on every decision-table row, including the Insights kinds and the `surface` rows. Evidence: `evidence/decision-table.txt`, plus `scripts/verify/opa.sh` output against the live sidecar.
- [ ] **A3.** Every decision row carries the `policy` extension with the bundle hash and the input hash. Evidence: `evidence/record-extension.txt`.
- [ ] **A4.** `scripts/verify/replay_decision.py` reproduces three stored decisions offline (one allow, one deny, one approval required). Evidence: `evidence/offline-replay.txt`.
- [ ] **A5.** With OPA stopped or slow, every action is denied `policy_unavailable`. An unsigned or changed bundle is refused. Evidence: `evidence/fail-closed.txt`.
- [ ] **A6.** The 024 purpose cases give the same stage and reason as before. "Approval required" is recorded and denied. Evidence: `evidence/no-behaviour-change.txt`.
- [ ] **A7.** The Policies page shows the engine, the bundle hash and the persona policies (Playwright). Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** The `docker stats` line for the OPA sidecar. Evidence: `evidence/memory.txt`.

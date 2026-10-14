# Sprint 032: Acceptance
- [ ] **A1.** All checks pass, including `opa test policy/`. The test delta is stated against Sprint 031's report. `check_skips` passes with the allowlist, with no new entries. Evidence: `evidence/checks.txt`.
- [ ] **A2.** A contract "must never" rule denies a matching agent action with `contract_must_never` on both engines. A free-text rule is refused at validation. Evidence: `evidence/must-never.txt`.
- [ ] **A3.** The AuthZEN 1.0 interop vectors pass for single and batch evaluation. Each evaluation writes a decision row. The discovery document at `/.well-known/authzen-configuration` answers without a credential and holds no tenant data, and the rule 9 decision is in `planning/DECISIONS.md` and `docs/architecture.md`. Evidence: `evidence/authzen-interop.txt`.
- [ ] **A4.** The test bench runs a draft against chosen inputs, and the draft never affects live traffic. Evidence: `evidence/test-bench.txt` and the Playwright run.
- [ ] **A5.** What-if over recorded inputs shows at least one changed decision for a narrowing draft. Publishing without a what-if is refused. Evidence: `evidence/what-if.txt`.
- [ ] **A6.** Replay matches the stored outcome for an allow, a deny and an approval required, in the UI and the CLI. Evidence: `evidence/replay.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** Not applicable: no new compose service.

# Sprint 036: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 035's report. `check_skips.py` passes with the allowlist. Evidence: `checks.txt`
- [ ] **A2.** The spike result is recorded, with the commands and redacted output, and the chosen issuer is named in ADR-0025. The spike ran with `--features=token-exchange-delegation` on the throwaway profile only, and ADR-0025 records the 2026-10-11 decision (platform-minted by default). Evidence: `spike-token-exchange.md`
- [ ] **A3.** A widening exchange (a scope the caller lacks) is refused with `delegation_widening` and a deny row. Evidence: `widening.txt`
- [ ] **A4.** A missing `may_act` and a second audience are each refused with their reason codes. Evidence: `may-act-audience.txt`
- [ ] **A5.** Token lifetime is bounded: `exp` is never after the run's end, and a token used after the run ends is refused. Evidence: `lifetime.txt`
- [ ] **A6.** Every decision of a run carries the delegation chain and the SPIFFE run id, in the API and on the run view (Playwright). Evidence: `chain.txt`, `playwright.txt`
- [ ] **A7.** A report run carries `sub=recipient`, `act=job:insights.report.run`, checked against `may_act` naming `insights.report` (`test_report_run_delegation_chain`). The delegation decision-table rows pass on both engines (`test_decision_table_delegation_rows`). Evidence: `report-run-chain.txt`, `decision-table.txt`
- [ ] **A-sec.** Every test in `threat-model.md` passes. Evidence: `threat-tests.txt`

## Notes
- Evidence is captured command output in `evidence/`, never hand-written.
- A check that needs a live service that cannot run here is marked "not verified here", with the verify script named and the reason.
- QA signs off `threat-model.md` before the sprint is accepted.

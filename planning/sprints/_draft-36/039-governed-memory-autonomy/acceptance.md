# Sprint 039: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 038's report. `check_skips.py` passes with the allowlist. `opa test` passes. Evidence: `checks.txt`
- [ ] **A2.** A poisoned memory write (an injection sample from a document) is quarantined, recorded as `memory_quarantined`, and never recalled. Evidence: `memory-quarantine.txt`
- [ ] **A3.** Recall for a sensitive purpose excludes low-tier items, and every recall writes a `memory.read` decision with the item ids. Evidence: `memory-recall.txt`
- [ ] **A4.** Seeded guardrail hits lower an agent's tier; the change has a decision row, a receipt that verifies and a `platform.agents.autonomy.changed.v1` event. The autonomy tier rows in the decision table pass on both engines (`test_decision_table_autonomy_tier_rows`). Evidence: `autonomy-tighten.txt`
- [ ] **A5.** A human admin reverses the tightening through `POST /v1/agent/{agent_id}/autonomy`; the change is recorded with the actor and reason, and the job never raises a tier. Evidence: `autonomy-reverse.txt`
- [ ] **A6.** An incident moves open, assessed, reported, closed, with each transition recorded and the Art. 73 fields filled (Playwright). Evidence: `incidents.txt`, `playwright.txt`
- [ ] **A7.** MC journey on the reference company with `scripts/showcase/mc.sh`: the salary question needs a human approval, the approver sees system evidence, an SSO user acts through a delegated run identity, MCP and A2A calls are governed, and guard models and governed memory are on. Evidence: `mc-journey.txt`
- [ ] **A-sec.** Every test in `threat-model.md` passes. Evidence: `threat-tests.txt`

## Notes
- Evidence is captured command output in `evidence/`, never hand-written.
- A check that needs a live service that cannot run here is marked "not verified here", with the verify script named and the reason.
- QA signs off `threat-model.md` before the sprint is accepted.

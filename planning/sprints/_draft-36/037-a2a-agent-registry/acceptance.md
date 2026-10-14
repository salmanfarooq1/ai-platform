# Sprint 037: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 036's report. `check_skips.py` passes with the allowlist. Evidence: `checks.txt`
- [ ] **A2.** A registered peer with a valid signed card completes `message/send` through `enforce()`, and the decision row carries the card digest. Evidence: `a2a-allowed.txt`
- [ ] **A3.** An unsigned card, a tampered card and a card signed by an unpinned key are each refused with their reason code and a deny row. Evidence: `card-refused.txt`
- [ ] **A4.** A changed card is blocked with `agent_card_changed` until an admin re-approves it in the registry (Playwright). Evidence: `card-reapproval.txt`, `playwright.txt`
- [ ] **A5.** The platform's own card is served and verifies with the published key. Evidence: `platform-card.txt`
- [ ] **A6.** The agentgateway spike result is recorded, and `pyproject.toml` and compose gained no agentgateway dependency. Evidence: `spike-agentgateway.md`
- [ ] **A-sec.** Every test in `threat-model.md` passes. Evidence: `threat-tests.txt`

## Notes
- Evidence is captured command output in `evidence/`, never hand-written.
- A check that needs a live service that cannot run here is marked "not verified here", with the verify script named and the reason.
- QA signs off `threat-model.md` before the sprint is accepted.

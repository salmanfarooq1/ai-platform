# Sprint 034: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 033's report. `check_skips.py` passes with the allowlist. Evidence: `checks.txt`
- [ ] **A2.** An approval works once for its exact action. A second use, and a use for a changed SQL, parameter, snapshot or purpose, each give a deny row with `approval_not_valid`. Evidence: `approval-binding.txt`
- [ ] **A3.** The requester cannot approve their own request (403 `separation_of_duties`, deny row), including a steward on their own product. Evidence: `separation-of-duties.txt`
- [ ] **A4.** An approved action that a later stage denies (cost cap, rate limit, revoked grant) is still denied. Evidence: `recheck.txt`
- [ ] **A5.** `POST /v1/agent/runs/{execution_id}/stop` ends a running run, revokes its run tokens, and writes an `agent.stop` decision and an oversight event. Override withholds the output. Evidence: `stop-override.txt`
- [ ] **A6.** The salary journey: the analyst's salary question gets `approval_required`, the steward sees an `approval_pending` item in `/v1/inbox`, approves in the approval queue, the re-run answers, and the receipt carries the approval extension. Over-limit queries now ask for approval. Evidence: `salary-journey.txt`, `playwright.txt`
- [ ] **A7.** An MCP client gets a URL-mode elicitation for a sensitive tool call. The AuthZEN response carries `context.approval`. Evidence: `mcp-elicitation.txt`, `authzen-approval.txt`
- [ ] **A8.** The approver view holds no agent-written text (a test plants text in the run's answer and checks the view). Evidence: `approver-view.txt`
- [ ] **A9.** `approval_required` on a dashboard, report or alert surface shows the tile `withheld` and creates no approval rows (`test_no_approval_rows_from_dashboards`). Evidence: `surface-withheld.txt`
- [ ] **A-sec.** Every test in `threat-model.md` passes. Evidence: `threat-tests.txt`

## Notes
- Evidence is captured command output in `evidence/`, never hand-written.
- A check that needs a live service that cannot run here is marked "not verified here", with the verify script named and the reason.
- QA signs off `threat-model.md` before the sprint is accepted.

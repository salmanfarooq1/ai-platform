# Sprint 027: Acceptance
- [ ] **A1.** All checks pass. The test delta is stated against Sprint 026's report. `check_skips` passes with the allowlist, with no new entries. Evidence: `evidence/checks.txt`.
- [ ] **A2.** A data run with any runtime but OpenShell is denied `sandbox_required`. A data run on OpenShell answers. Evidence: `evidence/sandbox-mandatory.txt` and `scripts/verify/openshell.sh` output, or "not verified here".
- [ ] **A3.** Accuracy on the 40+ question set is at or above the recorded threshold (Q40). The PR tier passes on the fake model, and the nightly tier ran once on the pinned local model. Evidence: `evidence/eval-pr.json` and `evidence/eval-nightly.json`.
- [ ] **A4.** The leakage tests pass: answers are the same with and without access to the masked column. The abstention cases abstain. Evidence: `evidence/eval-leakage.txt`.
- [ ] **A5.** A tainted run cannot call an outbound tool (`tainted_run_tool_blocked` row). Links and images are stripped from the answer. Evidence: `evidence/taint.txt`.
- [ ] **A6.** The answer receipt holds every field in scope item 3, including `group_by` and `filters` (`test_provenance_keeps_group_by_filters`), and is served at `/v1/receipts/{decision_id}`. Agent reads carry `surface=agent` (`test_agent_query_surface_agent`). Replay reproduces the result hash, and replay after revocation is denied. Evidence: `evidence/receipt-replay.txt`.
- [ ] **A7.** The Ask page shows the answer, the table, the provenance and the replay state (Playwright). Eval runs are stored signed and verify. Evidence: `evidence/playwright.txt` and `evidence/eval-signature.txt`.
- [ ] **A-sec.** The threat-model tests pass. The first garak and PyRIT nightly outputs are saved. Evidence: `evidence/threat-tests.txt` and `evidence/redteam/`.
- [ ] **A-mem.** The `docker stats` line for the worker and the sandbox during one local-model data run. Evidence: `evidence/memory.txt`.

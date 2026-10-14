# Sprint 022: Acceptance
- [ ] **A1.** All checks in the builder brief pass. Test delta stated against Sprint 021's report. `check_skips.py` passes with the allowlist. The licence gate passes with `ydata-profiling`. Evidence: `evidence/pytest-full.txt`, `evidence/check_skips.txt`, `evidence/licences.txt`.
- [ ] **A2.** A failing blocking check prevents certification: the transition is 403 `certification_blocked`, and the decision record's `data` extension names the evaluation and snapshot (`test_record_extension_data_fields`). After the data is fixed and re-evaluated, certification passes. Evidence: `evidence/certification-blocked.txt`.
- [ ] **A3.** The principal who moved a product to review, or its owner, cannot certify it: 403 `separation_of_duties`. Evidence: `evidence/separation.txt`.
- [ ] **A4.** A certified product degrades only after `QUALITY_DEGRADE_AFTER` bad evaluations and recovers only after `QUALITY_RECOVER_AFTER` good ones. A score oscillating around one threshold does not flap. Evidence: `evidence/hysteresis.txt`.
- [ ] **A5.** Profiling creates draft rules. A draft has no effect on the score until a steward approves it. Evidence: `evidence/drafts.txt`.
- [ ] **A6.** Every result and evaluation row carries a snapshot id that exists in the dataset's snapshot list. The app role cannot update or delete results. Evidence: `evidence/results-snapshots.txt`.
- [ ] **A7.** Quality page: score, checks, history, approve a draft (Playwright). Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** No new service. The worker's `docker stats` line during a profiling job is recorded. Evidence: `evidence/memory.txt`.

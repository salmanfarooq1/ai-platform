# Sprint 013: Acceptance
- [ ] **A1.** All checks pass with no behaviour change: every existing test passes unchanged except import paths. Test delta stated against Sprint 012's report. `check_skips` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** `lint-imports` passes on the tree and fails on the seeded violation. Evidence: `evidence/import-contracts.txt`.
- [ ] **A3.** Each edition boots and passes its smoke set (Gateway, Assurance, Agents, Data, Full) through `scripts/ci/edition_smoke.sh`, and `editions.yml` calls the script. Evidence: `evidence/editions.txt`.
- [ ] **A4.** Version 1 rows written before the migration and version 2 rows written after it verify in one chain, and their receipts verify offline with `scripts/verify/receipt.py`. Evidence: `evidence/record-v2.txt`.
- [ ] **A5.** With `ENABLED_MODULES=gateway`, `POST /v1/agent/query` answers 404 `module_disabled` and a deny row with that reason exists. `test_every_action_kind_maps_to_module` passes. Evidence: `evidence/module-disabled.txt`.
- [ ] **A6.** A failing `DecisionSink` on an allow gives 503 `decision_unrecorded`. Evidence: `evidence/sink-fail-closed.txt`.
- [ ] **A7.** Playwright: with agents disabled, the Agent runs link is hidden and Platform > Modules lists the module as off. Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

# Sprint 043: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 042's numbers. `check_skips.py` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** `check_mappings.py` passes on this sprint's JUnit file: every mapped row links to a passing test or an existing document. Evidence: `evidence/coverage.txt`.
- [ ] **A3.** The OWASP matrix shows no unowned ASI01–ASI10 or LLM01–LLM10 item. Seeded gaps (missing test, failed test, no owner) each fail the check. Evidence: `evidence/owasp-matrix.txt`.
- [ ] **A4.** A pack for the reference company system holds a system card, three model cards and an ML-BOM that validates against CycloneDX 1.6. Digests match `models.lock`. The system card's data-flow table has the Insights `report.deliver` row (`test_system_card_has_insights_data_flow`). Evidence: `evidence/pack-docs.txt`.
- [ ] **A5.** The release red-team run writes `redteam-summary.json` and the next pack includes it, or the run (or its Strix part, if Strix needs a hosted model key) is marked "not verified here" with the reason. The garak (`0.17.0`), PyRIT (`1.1.0`) and Strix pins and their OSI licences are in `evidence/pins.txt`. garak and PyRIT run from a separate venv or container and are not in `poetry.lock` (`test_redteam_tools_not_in_main_lock`). The licence override file covers garak. Evidence: `evidence/redteam.txt`.
- [ ] **A6.** The EU AI Act date test passes, and `check_eurlex.py` output is saved (or marked "not verified here" when offline). Evidence: `evidence/eurlex.txt`.
- [ ] **A7.** Playwright: Evidence > Compliance shows each framework and opens a row's evidence. Evidence: `evidence/e2e.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

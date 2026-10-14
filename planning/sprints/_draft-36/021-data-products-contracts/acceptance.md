# Sprint 021: Acceptance
- [ ] **A1.** All checks in the builder brief pass. Test delta stated against Sprint 020's report. `check_skips.py` passes with the allowlist. The licence gate passes with `datacontract-cli`. Evidence: `evidence/pytest-full.txt`, `evidence/check_skips.txt`, `evidence/licences.txt`.
- [ ] **A2.** An invalid contract is refused with 422 `contract_invalid` and a path-level error for each problem. Evidence: `evidence/contract-invalid.txt`.
- [ ] **A3.** The diff marks each breaking change as major: removed column, narrowed type, stricter rule, changed classification. Publishing it as a minor is refused. A major without a new output port is refused. Evidence: `evidence/contract-diff.txt`.
- [ ] **A4.** An illegal transition (for example `draft → certified`) is refused with 409. Moving to `in_review` without classification is refused with 422. Each legal transition writes one `product_events` row and one decision record. Evidence: `evidence/lifecycle.txt`.
- [ ] **A5.** Search finds the reference finance product by a column name and by a glossary term. Another tenant's search does not find it. Evidence: `evidence/search.txt`.
- [ ] **A6.** A stored contract version cannot be changed by the app role, and its hash matches the stored body. Evidence: `evidence/contract-immutable.txt`.
- [ ] **A7.** Products page: create, upload a contract, view a diff, move to review, search (Playwright). Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

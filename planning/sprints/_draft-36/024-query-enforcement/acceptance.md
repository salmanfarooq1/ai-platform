# Sprint 024: Acceptance
- [ ] **A1.** All checks in the builder brief pass. Test delta stated against Sprint 023's report. `check_skips.py` passes with the allowlist. Evidence: `evidence/pytest-full.txt`, `evidence/check_skips.txt`.
- [ ] **A2.** Every case in the bypass corpus (50 or more) gets its expected deny or masking. The count and categories are printed. Evidence: `evidence/bypass-corpus.txt`.
- [ ] **A3.** A masked column is never visible in clear: not through `*`, an alias, a function over it, a join or a set operation. Evidence: `evidence/masks.txt`.
- [ ] **A4.** An aggregate over a classified column returns no group with fewer than k rows. Evidence: `evidence/min-group.txt`.
- [ ] **A5.** A query with a purpose that differs from the grant's purpose is denied with `purpose_mismatch` and recorded. The decision row carries the `query` extension (hashes, grant ids and versions, purpose) and the snapshot id in `data` (`test_query_extension_fields`). Evidence: `evidence/purpose.txt`.
- [ ] **A6.** Two principals with different grants run the same SQL. Neither gets the other's cached result. A revoked grant interrupts a running query and the next one is denied. Evidence: `evidence/cache-isolation.txt`, `evidence/revoke-cancel.txt`.
- [ ] **A7.** Pruning still prunes: on a month-partitioned table, the rewritten query reads the same number of data files as the original. Evidence: `evidence/pruning.txt`.
- [ ] **A8.** Data query page: run a query with a purpose, see masked badges and the decision link (Playwright). Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

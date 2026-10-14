# Sprint 015: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 014's report. `check_skips` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** The generators are deterministic: the manifest hash for each size and seed equals `checksums.json` on two runs. Evidence: `evidence/determinism.txt`.
- [ ] **A3.** No real names or brands: the deny-list scan of every CSV and PDF is clean, and all email domains are reserved. Evidence: `evidence/deny-list.txt`.
- [ ] **A4.** `refco_source` loads the small set in the `lake` profile, and the change generator applies its steps. Evidence: `evidence/refco-source.txt`.
- [ ] **A5.** `scripts/showcase/m0.sh` passes end to end on a local stack. Evidence: `evidence/m0-journey.txt`.
- [ ] **A6.** Playwright `showcase-m0.spec.ts` passes. Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats --no-stream` for `refco-source`. Evidence: `evidence/memory.txt`.

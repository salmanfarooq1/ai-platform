# Sprint 023: Acceptance
- [ ] **A1.** All checks in the builder brief pass. Test delta stated against Sprint 022's report. `check_skips.py` passes with the allowlist. Evidence: `evidence/pytest-full.txt`, `evidence/check_skips.txt`.
- [ ] **A2.** No grant exists without an approved request: every `grants` row links to a request whose steps are all approved with the same hash. A direct insert by the app role is refused. Evidence: `evidence/grant-provenance.txt`.
- [ ] **A3.** The requester cannot approve their own request, nor can the product owner or its certifier: 403 `separation_of_duties`. Evidence: `evidence/separation.txt`.
- [ ] **A4.** Two approvers acting on the same step at once: one wins, one gets 409. An approval that quotes an old hash after the request changed gets 409 `request_changed`. Evidence: `evidence/approval-races.txt`.
- [ ] **A5.** A grant past `expires_at` gives `grant_expired` even before the expiry job runs. A revoked grant blocks the next extract with `grant_revoked`, and its extract objects are gone. Evidence: `evidence/expiry-revoke.txt`.
- [ ] **A6.** An extract, made through `DataAccess.extract`, holds only granted, unmasked columns and filtered rows (`test_extract_respects_grant`). Its decision row has the `access` extension with request and grant ids (`test_record_extension_access`). Its URL stops working after `EXTRACT_URL_TTL_SECONDS`. Evidence: `evidence/extracts.txt`.
- [ ] **A7.** Marketplace, My access and Approvals: request, approve as a second persona, download (Playwright). Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

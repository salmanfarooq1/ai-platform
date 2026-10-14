# Sprint 035: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 034's report. `check_skips.py` passes with the allowlist. Evidence: `checks.txt`
- [ ] **A2.** OIDC sign-in works end to end against the fake issuer (pytest and Playwright), and against Keycloak with `scripts/verify/keycloak.sh` (or marked "not verified here" with the reason). Evidence: `sso-signin.txt`, `keycloak-verify.txt`, `playwright.txt`
- [ ] **A3.** The group mapping test passes, and fails on a seeded extra group in the realm export. A `bi-authors` user gets `data:read` and `insights:write` (`test_bi_authors_persona_scopes`). Evidence: `role-mapping.txt`
- [ ] **A4.** A service client gets a token with client credentials and calls a `/v1` route with the mapped scopes. An API key and an existing JWT still work. Evidence: `service-client.txt`
- [ ] **A5.** Each anti-pattern test passes, and `scripts/verify/mutate_identity.py` shows each one fails when its protection is removed (TLS, state, alg none, HS256 on the OIDC path, debug bypass, default password). The existing HS256 path for API JWTs is not changed and is not part of this list. Evidence: `antipatterns.txt`, `mutations.txt`
- [ ] **A6.** Sign-in stores `last_scopes` and `last_seen_at`. A report recipient not seen within `IDENTITY_STALE_DAYS` gets a denied `report.deliver` and no file (`test_stale_recipient_report_denied`). Evidence: `stale-recipient.txt`
- [ ] **A7.** The realm export holds no secret and no password (gitleaks and a scan test). Evidence: `realm-scan.txt`
- [ ] **A-sec.** Every test in `threat-model.md` passes. Evidence: `threat-tests.txt`
- [ ] **A-mem.** `docker stats` line for Keycloak. Evidence: `docker-stats.txt`

## Notes
- Evidence is captured command output in `evidence/`, never hand-written.
- A check that needs a live service that cannot run here is marked "not verified here", with the verify script named and the reason.
- QA signs off `threat-model.md` before the sprint is accepted.

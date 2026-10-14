# Sprint 035: Threat model

## Assets
- The browser session cookie and CSRF token. The OIDC client secret.
- The mapping from groups to scopes. The link from external subjects to principals and tenants.
- The Keycloak admin account.

## Trust boundaries crossed
- Browser to web edge (redirects, callback parameters).
- Web edge to Keycloak (code exchange, discovery, JWKS).
- Service clients to the API (bearer tokens from the provider).

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Forged token with `alg: none` | Spoofing | Algorithm allow-list RS256, ES256, PS256 | `test_oidc_rejects_alg_none` |
| T2 | HS256 token signed with the public key as secret | Spoofing | Symmetric algorithms refused on the OIDC path. The existing HS256 path for API JWTs is a separate verifier, untouched here (open question). | `test_oidc_rejects_symmetric` |
| T3 | Login CSRF: attacker's code injected into the victim's browser | Spoofing | `state` stored by hash, single use, fail closed with no code exchange | `test_state_mismatch_no_exchange` |
| T4 | Authorization code intercepted | Spoofing | PKCE S256 verifier kept server side | `test_code_without_verifier_fails` |
| T5 | ID token replay | Spoofing | `nonce` bound to the stored state | `test_nonce_mismatch_rejected` |
| T6 | TLS checks turned off to "fix" a dev setup | Tampering | No setting exists; the HTTP client is built with verification on | `test_no_tls_verify_off` (code scan and client check) |
| T7 | Debug or local mode skips token checks | Elevation | Same checks in every `MODE` | `test_local_mode_still_verifies` |
| T8 | A group in the provider not in the code grants nothing, or a typo grants too much | Elevation | One mapping file; startup refuses unknown scopes; group test both ways | `test_role_mapping_matches_realm` |
| T9 | Tenant chosen by the token holder | Elevation | Tenant only from the signed claim, and the link row must be in that tenant | `test_tenant_claim_must_match_link` |
| T10 | Default admin password on Keycloak | Elevation | Password only from a mounted file; compose fails without it; export has no credentials | `test_realm_export_has_no_credentials` |
| T11 | Provider down and sign-in falls back to something weaker | DoS / Elevation | 503 `oidc_unavailable`, no fallback | `test_provider_down_fails_closed` |
| T12 | Sign-in attempts leave no trace | Repudiation | `session.create` decision rows for success and failure | `test_signin_decisions_recorded` |
| T13 | A leaver keeps getting reports because their scopes are no longer checked at sign-in | Elevation | `last_scopes` and `last_seen_at` per identity; past `IDENTITY_STALE_DAYS` the recipient is treated as disabled | `test_stale_recipient_report_denied` |

## Abuse cases
- An attacker links their own provider account to a victim principal. Links are made only by first sign-in in the claimed tenant, or by the admin CLI for service clients.
- Open redirect through `OIDC_REDIRECT_URL`. The redirect is a fixed setting; the callback never takes a return URL from the query.

## OWASP items in scope
- ASI03 Identity and privilege abuse: T8, T9.
- LLM Top 10: none. No model input or output changes in this sprint.

## Residual risks
- A live session keeps its scopes until it ends (ADR-0007). A group change in the provider applies at the next sign-in.
- The existing `JWT_SECRET` HS256 path stays for current JWT clients. Open question.

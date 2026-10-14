# Sprint 020: Identity and access. Requirements

Gateway pillar (Kernel and M1), with M3 run identity. Console sign-in through Keycloak, SCIM provisioning, MFA, custom and auditor roles, and session and network rules. Agent runs act for a user through delegation tokens that only narrow, with a run identity and a chain on every decision.

Source: old 035, old 036, plus new scope (enterprise-gaps-how and gateway-proxy-and-agents research notes, bundle B).

## Scope
1. **Keycloak in profile `identity`.**
   - `quay.io/keycloak/keycloak:26.8.x`, pinned by digest and at least two weeks old at sprint start. It replaces the 26.7.4 pin because 26.8.0 makes SCIM supported.
   - Port bound to `127.0.0.1`. A realm export in the repo with no secrets, no users and no passwords.
   - Console sign-in with OIDC (authorization code + PKCE) through the web edge. The ADR-0007 session stays the browser model.
2. **SCIM 2.0 provisioning (inbound).**
   - Keycloak's built-in SCIM server (`/realms/<realm>/scim/v2`, realm opt-in) receives users and groups from Okta or Entra.
   - Conformance tests run in CI against a Keycloak container, with Okta- and Entra-shaped requests.
   - Deprovisioning reaches the platform: a disabled or deleted user loses console sessions and personal API keys within `IDENTITY_DEPROVISION_SECONDS`. The mechanism (admin events, polling, or short sessions plus a check) is picked in the blueprint and recorded in ADR-0025.
   - Outbound SCIM is out of scope (Keycloak has no SCIM client yet).
3. **Roles.**
   - Keycloak roles and groups map to platform scopes through one mapping file. A test checks the realm export and the mapping file match both ways.
   - Custom roles are data: a tenant admin defines a role as a named set of scopes, with no code change.
   - A read-only `auditor` role reads audit, receipts and evidence. It never gets grants, runs or row-data export. This is enforced in policy (018).
   - Each sign-in stores `last_scopes` and `last_seen_at`. Report and alert runs (029) use them. A recipient not seen within `IDENTITY_STALE_DAYS` is treated as disabled.
4. **MFA, sessions and network.**
   - Enforced MFA flow (OTP or WebAuthn), brute-force lockout, session idle and max limits in the realm.
   - IP allowlist per tenant, enforced in the app and at the 016 proxy. Forwarded headers are overwritten at the edge, so they cannot be spoofed. Keycloak has no native IP allowlist.
5. **Service clients.** Automation uses the client credentials grant. API keys and existing JWTs keep working.
6. **Delegation tokens (decided 2026-10-11).**
   - A `DelegationIssuer` port with one contract suite.
   - The default adapter is platform-minted EdDSA JWTs carrying the `act` chain.
   - A spike checks Keycloak 26.8 token exchange with `actor_token` on a throwaway profile only. A Keycloak adapter is built only if nested delegation is no longer a preview feature. Preview features never run in the default stack.
   - Rules, each with tests: `may_act` is checked before any exchange, the audience is limited to one downstream per token, the lifetime is at most the run's, and each hop only narrows scopes.
7. **Run identity and chain.**
   - SPIFFE-format run ids, `spiffe://<trust-domain>/tenant/<tenant_id>/run/<execution_id>`, without SPIRE.
   - The delegation chain is stored on every decision a run causes (record v2 extension `delegation`) and goes into `PolicyInput`, with decision-table rows for both engines.
   - Report runs (029) are delegations: `sub` is the recipient and `act` is `job:insights.report.run`.
   - The 016 request contract now accepts the `act` chain from these tokens.
8. **Test tooling and anti-pattern tests.**
   - A fake OIDC issuer with JWKS for pytest. `scripts/verify/keycloak.sh` runs nightly.
   - Each anti-pattern test fails when its protection is removed: TLS verification never off, a failed state check fails closed, no unsigned or symmetric tokens on the OIDC path, no debug bypass, no default passwords, no preview features in the `identity` profile.

## Out of scope
- User management screens. Users and groups live in the identity provider.
- SPIRE, workload attestation and X.509 SVIDs (documented as an optional later step).
- A2A identities (028). FIPS crypto.
- Changed from old 035 and 036: the Keycloak pin is 26.8.x, delegation is decided (platform-minted), and SCIM, MFA, custom and auditor roles and the IP allowlist are new.

## Nav placement
- Platform > Identity: provider status, clients (ids only), the role mapping, custom roles, MFA and session policy, and IP allowlists.
- The sign-in page gains "Sign in with single sign-on".
- Governance > Agent runs: a "Delegation chain" panel on the run view.

## Questions this sprint closes
- Opens one: should the existing `JWT_SECRET` HS256 path be refused in `prod` now that an asymmetric provider exists?
- Opens one for the owner: is inbound SCIM enough, or must the platform push changes back out?

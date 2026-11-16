# Sprint 020: Identity and access. Requirements

Gateway pillar (Kernel and M1), with M3 run identity. Console sign-in through the client's own identity provider with a standard OIDC client, SCIM 2.0 provisioning, MFA at the provider, custom and auditor roles, and session rules. Agent runs act for a user through delegation tokens that only narrow, with a run identity and a chain on every decision.

Source: old 035, old 036, plus new scope (enterprise-gaps-how and gateway-proxy-and-agents research notes, bundle B).

Depends on: 019.

## Scope
1. **OIDC client against any standard provider** (`IDP=oidc`).
   - Console sign-in with OIDC (authorization code + PKCE) through the web edge. The ADR-0007 session stays the browser model.
   - Issuer discovery, JWKS caching with rotation, and per-tenant issuer settings. Tested against Entra ID and Okta claim shapes with recorded fixtures.
   - Entra group overage: when the token carries the overage claim instead of groups (over 200), fetch the groups from Microsoft Graph with a least-privilege app permission. A failed fetch fails closed.
   - Keycloak (`quay.io/keycloak/keycloak:26.8.x`, pinned by digest, at least two weeks old) is the **test issuer only**, in profile `identity`, used by CI and nightly. Port bound to `127.0.0.1`. A realm export in the repo with no secrets, no users and no passwords. It is never part of the shipped default stack.
2. **Roles and subject-scoped policy.**
   - Provider roles and groups map to platform scopes through one mapping file per tenant. A test checks the test realm export and the mapping file match both ways.
   - The platform admin role comes from verified issuer claims.
   - Custom roles are data: a tenant admin defines a role as a named set of scopes, with no code change.
   - A read-only `auditor` role reads audit, receipts and evidence. It never gets grants, runs or row-data export. This is enforced in policy (018).
   - The policy document and decision table support rules by user, group, role and agent id.
   - Each sign-in stores `last_scopes` and `last_seen_at`. Report and alert runs (029) use them. A recipient not seen within `IDENTITY_STALE_DAYS` is treated as disabled.
3. **MFA and sessions.**
   - MFA, brute-force lockout and provider session limits stay with the identity provider. We check the `amr` or `acr` claim against the tenant's required level and fail closed. Our own session idle and max limits stay.
4. **Service clients.** Automation uses the client credentials grant. API keys and existing JWTs keep working.
5. **Delegation tokens and issuer keys.**
   - A `DelegationIssuer` port with one contract suite.
   - The default adapter is platform-minted EdDSA JWTs carrying the `act` chain.
   - Rules, each with tests: `may_act` is checked before any exchange, the audience is limited to one downstream per token, the lifetime is at most the run's, and each hop only narrows scopes.
   - Manage issuer keys, rotation and JWKS for platform-minted delegation and downstream tokens.
6. **Run identity and chain.**
   - Each run has a stable run id. Its delegation chain is stored on every decision it causes (record v2 extension `delegation`) and goes into the policy input.
   - Report runs (029) are delegations: `sub` is the recipient and `act` is `job:insights.report.run`.
   - The 016 request contract now accepts the `act` chain from these tokens.
7. **SCIM 2.0 inbound** (moved from 030).
   - `/scim/v2/Users` and `/scim/v2/Groups` with a per-tenant bearer token. Create, update, deactivate and delete.
   - A disabled or deleted user loses console sessions and personal API keys within `IDENTITY_DEPROVISION_SECONDS`.
8. **Test tooling and anti-pattern tests.**
   - A fake OIDC issuer with JWKS for pytest. `scripts/verify/keycloak.sh` runs nightly.
   - Each anti-pattern test fails when its protection is removed: TLS verification never off, a failed state check fails closed, no unsigned or symmetric tokens on the OIDC path, no debug bypass, no default passwords, no preview features in the `identity` profile.

## Out of scope
- User management screens. Users and groups live in the identity provider.
- IP allowlist, SPIFFE ids and the token-exchange spike (030).
- Shipping or operating Keycloak for clients.
- SPIRE, workload attestation and X.509 SVIDs (documented as an optional later step).
- A2A identities (028). FIPS crypto.
- Changed from old 035 and 036: the Keycloak pin is 26.8.x, delegation is platform-minted, and OIDC sign-in and subject-scoped policy are in scope.
- Re-planned 2026-11-08: see "Re-plan 2026-11-08" in `planning/program/sprint-map.md` and ADR-0035. Keycloak became the test issuer only; SCIM moved here from 030; Entra group overage added.

## Nav placement
- Platform > Identity: provider status, clients (ids only), the role mapping, custom roles, MFA and session policy.
- The sign-in page gains "Sign in with single sign-on".
- Governance > Agent runs: a "Delegation chain" panel on the run view.

## Questions this sprint closes
- Opens one: should the existing `JWT_SECRET` HS256 path be refused in `prod` now that an asymmetric provider exists?

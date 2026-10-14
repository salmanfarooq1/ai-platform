# Sprint 035: Identity and single sign-on. Requirements

A vertical slice in the Kernel and M1 Gateway: console sign-in through an external OpenID Connect provider, role mapping, service clients and the portal anti-pattern tests.

## Scope
1. **Keycloak in profile `identity`.**
   - `quay.io/keycloak/keycloak:26.7.4`, pinned by digest, port bound to `127.0.0.1`.
   - A realm export in the repo with no secrets, no users and no passwords.
   - Console sign-in with OIDC (authorization code + PKCE) through the web edge. The ADR-0007 session stays the browser model.
2. **Role mapping.** Keycloak roles and groups map to platform scopes through one mapping file. A test checks that every group name in the realm export is in the mapping file, and the other way round.
   - The group `bi-authors` maps to `data:read` and `insights:write`, for dashboard and report authors (028, 029).
   - Each sign-in stores the identity's `last_scopes` and `last_seen_at`. Report and alert runs (029) act as the recipient and use these. A recipient not seen within `IDENTITY_STALE_DAYS` is treated as disabled.
3. **Service clients.** Automation uses the client credentials grant. API keys and existing JWTs keep working.
4. **Test tooling.**
   - A fake OIDC issuer with JWKS for pytest.
   - `scripts/verify/keycloak.sh` runs nightly in CI.
5. **Portal anti-pattern tests.** Each fails when its protection is removed.
   - TLS verification is never off.
   - A failed state check fails closed.
   - No unsigned or symmetric tokens on the OIDC path.
   - No debug bypass.
   - No default passwords.

## Out of scope
- Delegation, token exchange and run identities (Sprint 036).
- User management screens. Users and groups live in the identity provider.
- Changing the existing `JWT_SECRET` (HS256) path for current JWT clients (see Questions).

## Nav placement
Platform > Identity: provider status, clients (ids only), and the role mapping table, read-only. The sign-in page gains "Sign in with single sign-on".

## Questions this sprint closes
- None closed. Opens one: should the existing `JWT_SECRET` HS256 path be refused in `prod` now that an asymmetric provider exists?

# Sprint 035: Blueprint

## Contract
- `GET /v1/session/oidc/start` (public): makes `state`, `nonce` and a PKCE S256 verifier, stores them in Valkey under `oidcstate:<sha256(state)>` (TTL 600 s, single use), and redirects to the provider.
- `GET /v1/session/oidc/callback?code&state` (public): no stored state, a used state, or a mismatch answers 400 `oidc_state_invalid` and never exchanges the code. Otherwise it exchanges the code with the verifier, verifies the ID token, maps groups to scopes, and creates the same `gap_session` cookie and CSRF token as `POST /v1/session`.
- `AuthMiddleware` lets exactly these two paths through, next to the two session paths it already allows.
- `GET /v1/identity/provider` (`admin`): issuer, client ids, mapping table, last JWKS fetch time. No secrets.
- Bearer tokens from the provider (service clients and users) are accepted when their issuer is `OIDC_ISSUER_URL`, with asymmetric algorithms only. The existing `JWT_SECRET` (HS256) path for API JWTs stays as it is, keyed apart by issuer.
- Error codes: `oidc_state_invalid`, `oidc_token_invalid`, `oidc_unmapped` (no group maps to a scope), `oidc_unavailable` (503, fail closed). OpenAPI snapshot refreshed.

## Identity
- `core/identity/oidc.py`: discovery, JWKS cache, code exchange, ID token and access token checks. Algorithms: RS256, ES256, PS256 only. `iss`, `aud`, `exp`, `iat`, `nonce` (ID token) required.
- External subjects link to principals. Tenant comes from a `tenant_id` claim set by a protocol mapper in the realm export (a user attribute). The platform checks that the tenant exists and that the link row is in that tenant (strict rule 1).
- First sign-in creates a `user` principal linked to `(issuer, subject)` when the user's groups map to at least one scope. Scopes come from groups on every sign-in and token. The request uses the fresh scopes. Each sign-in also stores them as `last_scopes` with `last_seen_at`, for runs that act on behalf of the user.
- Service clients: a `service` principal linked to the client's service account subject, created with `scripts/admin/identity.py link-client`.
- `config/identity/role-mapping.yaml`: `groups: {<group>: [scopes]}`. Unknown scopes are refused at startup. Unknown groups grant nothing. It includes `bi-authors: [data:read, insights:write]`.
- Report and alert runs (029) act as the recipient's principal with `last_scopes`. A recipient whose `last_seen_at` is older than `IDENTITY_STALE_DAYS` is treated as disabled: `report.deliver` denies as for a disabled principal, the run records it, and nothing is delivered. Before this sprint, API-key principals keep their stored scopes.

## Settings (validated in `core/settings.py`)
`OIDC_ISSUER_URL` (https unless `MODE=local` with a `127.0.0.1` or compose host), `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET_FILE` (file-mounted), `OIDC_REDIRECT_URL`, `IDENTITY_ROLE_MAPPING_FILE`, `IDENTITY_STALE_DAYS` (a placeholder default with a question in `planning/QUESTIONS.md`). No setting turns off TLS checks or token checks.

## Data (migration: next free number after Sprint 034's head)
- `external_identities`: `id`, `tenant_id`, `issuer`, `subject`, `principal_id`, `kind` (user, service), `created_at`, `last_seen_at`, `last_scopes text[]`. Unique `(issuer, subject)`. FORCE RLS. GRANT SELECT, INSERT, UPDATE (`last_seen_at`, `last_scopes`) to `gap_app`.
- A narrow SECURITY DEFINER `auth_lookup_external(issuer, subject)` in the pattern of `auth_lookup_key`, for the lookup before a tenant context exists.

## Gateway
New action kind `session.create` (introduced here): sign-in success and failure are `session.create` decisions with reason codes `allowed`, `oidc_state_invalid`, `oidc_token_invalid`, `oidc_unmapped`. Added to `gateway/reasons.py`.

## Compose and scripts
- Profile `identity`: `keycloak` with `start --import-realm`, healthcheck on the management port, admin password from `KEYCLOAK_ADMIN_PASSWORD_FILE`. Compose refuses to start the service without it.
- `deploy/keycloak/realm.json` (the export). `scripts/verify/keycloak.sh`: boot, import, PKCE sign-in with a test user created by the script, client credentials call, one denied call. Nightly CI job; `docker stats` line saved.

## UI (follow `.claude/skills/governed-design/SKILL.md`)
Sign-in page button; Platform > Identity page; a clear error page for each sign-in error code.

## Tests
- `tests/fake_oidc.py`: an in-process issuer with discovery, JWKS, authorize and token endpoints, served through the HTTP client transport. It can mint good and bad tokens.
- Unit and integration: PKCE flow; state single use; nonce check; group mapping test; `test_bi_authors_persona_scopes` (a `bi-authors` user gets `data:read` and `insights:write` and can publish a dashboard); `test_last_scopes_stored_on_sign_in`; `test_stale_recipient_report_denied` (a recipient past `IDENTITY_STALE_DAYS` gets no report); RLS on `external_identities`; API keys and existing JWTs unchanged.
- Anti-pattern tests (`tests/integration/test_identity_antipatterns.py`) and `scripts/verify/mutate_identity.py`, which removes each protection in a temp copy and shows the matching test fails.
- Playwright: sign in with SSO against the fake issuer, land on the console.

## Docs
`docs/configuration.md` (OIDC settings), `docs/operations.md` (Keycloak profile, realm import, mapping file), `docs/adr/0007-web-edge-session.md` (append: OIDC sign-in). ADR-0025 in Sprint 036 records the provider choice; this sprint adds a `planning/DECISIONS.md` entry.

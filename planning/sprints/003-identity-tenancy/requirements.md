# Sprint 003: Identity and tenancy — Requirements

## Goal
Every request is made by an authenticated principal that belongs to exactly one tenant, and Postgres row-level security makes cross-tenant reads and writes impossible, even if app code forgets a filter.

## Why it matters
Today any caller picks any namespace (gap 1). Every later layer (gateway policy, budgets, receipts, jobs) keys off the principal and tenant, so this must exist first.

## Scope
1. **Tables (migration 0002):** `tenants`, `principals` (user/service/agent, belongs to one tenant), `api_keys` (prefix, SHA-256 hash of the secret, scopes, revoked_at, last_used_at), `knowledge_bases` (tenant-owned; replaces `NAMESPACE_REGISTRY`). Add non-null `tenant_id` to `documents`, `document_registry`, `usage_log`, `feedback`. Backfill existing rows to one tenant `default` and seed its KBs from today's three namespaces.
2. **Row-level security:** `ENABLE` + `FORCE ROW LEVEL SECURITY` on every tenant-owned table; policy `tenant_id = current_setting('app.tenant_id')::uuid`. Missing setting → zero rows (fail closed).
3. **Tenant-scoped DB access:** one helper (`tenant_connection(pool, tenant_id)`) opens a transaction and runs `SET LOCAL app.tenant_id`. All request-path queries go through it.
4. **Non-privileged app role:** RLS does not apply to superusers or `BYPASSRLS` roles. Startup checks the connected role and **refuses to start** if it is superuser or has `BYPASSRLS`. Local compose and tests create and use a non-superuser login role; migrations run as the owner role.
5. **Authentication:** `Authorization: Bearer <token>` where the token is an API key (`gap_<prefix>_<secret>`) or a JWT (verified with `JWT_JWKS_URL` or `JWT_SECRET`, issuer + audience checked). Result is a `Principal(id, tenant_id, kind, scopes)` on `request.state`. Tenant comes only from the verified credential.
6. **Authorization (coarse):** scopes `kb:read`, `kb:write`, `query`, `agent`, `admin`. Each `/v1` route declares its scope. Missing/invalid credential → 401; missing scope → 403; KB not in caller's tenant → 404 (same body as a non-existent KB, no existence leak).
7. **Rate limit and token budget** key on tenant (and principal), not on a caller-supplied namespace.
8. **MCP** requires the same bearer credential.
9. **Admin CLI:** `scripts/admin/` commands to create a tenant, a principal, an API key (secret printed once, only hash stored), and revoke a key.
10. **Public preview access:** the UI's nginx proxy adds a server-side API key (`PREVIEW_API_KEY`, a Render secret on the UI service) so browsers never hold it. That key is scoped to the preview tenant.

## Out of scope
The `enforce()` pipeline and policy engine (004), login UI and user sign-up, OAuth flows (we only verify tokens), per-KB ACLs inside a tenant.

## Rules that apply
1, 2, 3, 7, 8, 14. Working agreements.

## Edge cases
- Revoked or unknown key, wrong-prefix key, expired JWT, JWT with wrong `aud`/`iss`, `alg=none` → 401.
- Header `X-Tenant-ID`, `?tenant_id=`, or body `tenant_id` are ignored (test this).
- Query with tenant A credential for tenant B's KB slug that also exists in A → returns only A's data.
- Hosted DB: migration backfills; existing data stays readable by the `default` tenant.

## Open questions
See `planning/QUESTIONS.md` Q5–Q6.

## Added during blueprint
11. **Caches are tenant-scoped.** The exact-match and semantic caches in `api/services/cache.py` must include `tenant_id` in every key and in the semantic index filter. Otherwise tenant B gets tenant A's cached answer, and row-level security can't catch it.

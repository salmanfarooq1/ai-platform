# Sprint 003: Identity and tenancy — Blueprint

## Read first
`AGENTS.md`, `FOUNDATION.md` §3, ADR-0003, `core/settings.py`, `core/database/pool.py`, `migrations/versions/0001_baseline.py`, `api/main.py`, `api/dependencies.py`, `api/errors.py`, all `api/routers/*.py`, `api/middleware/rate_limit.py`, `token_budget.py`, `finops.py`, `api/services/cache.py`, `api/services/retriever.py`, `api/services/usage.py`, `core/ingestion/lifecycle.py`, `core/pipeline/*.py`, `api/agent/tools.py`, `api/mcp/*.py`, `tests/harness.py`, `tests/db_fixtures.py`, `docker-compose.yml`, `ui/nginx.conf`, `ui/Dockerfile.ui`, `render.yaml`.

## New modules
| Path | Purpose |
|---|---|
| `migrations/versions/0002_identity_tenancy.py` | Tables, `tenant_id` columns, backfill, RLS policies |
| `core/identity/models.py` | `Principal`, `Scope` (typed, frozen) |
| `core/identity/keys.py` | Key format `gap_<8-char prefix>_<32+ char secret>`, generate, SHA-256 hash, constant-time compare |
| `core/identity/jwt.py` | JWT verify (PyJWT): JWKS URL or HS secret; require `exp`, `iss`, `aud`; reject `none` |
| `core/identity/store.py` | Look up the key by prefix, check hash and revocation, load principal (runs as a narrow `SECURITY DEFINER` function, or a dedicated lookup that does not need a tenant) |
| `core/database/tenant.py` | `async with tenant_connection(pool, tenant_id) as conn:` → transaction + `SET LOCAL app.tenant_id` |
| `api/auth.py` | `authenticate` dependency → `Principal`; `require_scope(scope)` dependency |
| `scripts/admin/identity.py` | CLI: `create-tenant`, `create-principal`, `create-key` (prints secret once), `revoke-key`, `list-keys` |

## Schema (migration 0002)
- `tenants(id uuid pk, slug text unique, name, created_at)`
- `principals(id uuid pk, tenant_id fk, kind text check in ('user','service','agent'), name, created_at, disabled_at)`
- `api_keys(id uuid pk, tenant_id, principal_id fk, prefix text unique, secret_hash text, scopes text[], created_at, last_used_at, revoked_at)`
- `knowledge_bases(id uuid pk, tenant_id, slug, description, created_at, unique(tenant_id, slug))`
- Add `tenant_id uuid not null references tenants` to `documents`, `document_registry` (the PK becomes `(tenant_id, namespace, document_id)`), `usage_log` and `feedback`. Backfill to the `default` tenant, seeded with KBs `legal`, `kyc_aml`, `default`. Indexes lead with `tenant_id`.
- RLS: `ENABLE` + `FORCE` on the tenant-owned tables (the 4 above, plus `knowledge_bases`, `principals` and `api_keys`). Policy `USING` and `WITH CHECK` on `tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid`.
- Key lookup before the tenant is known: a `SECURITY DEFINER` function `auth_lookup_key(prefix)` owned by the migration role. It returns only the columns needed to verify. This is the one audited bypass.
- The migration does not create login roles or passwords. Roles are environment setup (below).

## Roles
- **Local and tests:** a compose init script (`docker/postgres-init/01-app-role.sql`) and the test harness create the login role `gap_app`. It is `NOSUPERUSER NOBYPASSRLS`, gets DML grants on the tables, and gets default privileges for future tables. The password comes from env (`APP_DB_PASSWORD`, local default `gap_app`).
- **Settings:** `DATABASE_URL` is the app role, used at runtime. `MIGRATION_DATABASE_URL` is the owner role, used by Alembic and admin, and falls back to `DATABASE_URL`.
- **Startup guard:** query `select rolsuper, rolbypassrls from pg_roles where rolname = current_user`. If either is true, the app refuses to start. This applies in every mode.
- **Dockerfile CMD:** `alembic upgrade head` uses `MIGRATION_DATABASE_URL`.

## Request flow
`Authorization` header → `authenticate` → `Principal` on `request.state.principal` → the route's `require_scope` → the handler gets `tenant_id` only from the principal → every DB call goes through `tenant_connection`. The `namespace` parameter remains, but means a KB slug that is checked against the tenant's `knowledge_bases`. An unknown or foreign KB gives 404 `kb_not_found`.

## Changes in existing code
- Retriever, ingestion, lifecycle, docs, analytics, feedback, usage and agent tools: use `tenant_connection` and remove all reliance on `NAMESPACE_REGISTRY` (delete it). `list_namespaces` reads the caller's KBs.
- Caches: key = `tenant_id` + the existing parts. The semantic index stores `tenant_id` as a TAG field and filters on it.
- Rate limit and budget: key on `tenant_id` (budget) and `principal_id` (rate). These run after authentication, so move them to dependencies or make the middleware read `request.state.principal`. Unauthenticated requests get 401 before any limiter runs.
- MCP SSE and messages require the bearer token. The tools use the principal's tenant.
- `/health`, `/`, `/v1/health` and `/docs`/`openapi.json` stay public. Every other `/v1` route requires auth.
- UI: `ui/nginx.conf` becomes an envsubst template that sets `Authorization: Bearer ${PREVIEW_API_KEY}` on `/api/` (proxy only, so the browser never sees it). `render.yaml` gets `PREVIEW_API_KEY` (`sync: false`) on the UI service and `MIGRATION_DATABASE_URL` (`sync: false`) on the API. Local dev: `ui/vite.config` proxy adds the header from `.env.local` `PREVIEW_API_KEY`.

## Test plan (real Postgres and Redis, fakes for LLM and embeddings)
Fixtures: two tenants A and B, each with keys of different scopes. The app connects as `gap_app` (non-superuser) so RLS really applies.

**Integration:**
- RLS: with A set, `select` from each tenant table returns only A rows. With no setting, 0 rows. An insert with B's `tenant_id` under A fails.
- Startup guard: connecting as `postgres` (superuser) raises at startup.
- Migration: `0001` → `0002` on a DB with existing rows backfills to `default` and keeps the row counts.
- Key lookup: valid, wrong secret, revoked and unknown prefix.

**Unit:** key generation, hashing and format. JWT: valid, expired, wrong aud, wrong iss, `alg=none`, bad signature. Scope checks.

**E2E (HTTP):**
- No header → 401 and the error body. A bad key → 401. A good key missing the scope → 403.
- A ingests `gdpr.md` into `legal`. B searches `legal` and gets no A content (0 results). B lists documents and gets an empty list. A gets its document.
- A spoofs `X-Tenant-ID: <B>`, `?tenant_id=` and a body `tenant_id`: nothing changes.
- Cache isolation: A searches (MISS, then HIT). B runs the same query → MISS, no A content. The semantic near-duplicate is also a MISS for B.
- A foreign KB and a non-existent KB give byte-identical 404 bodies, except for `request_id`.
- Budget and rate limit count per tenant and principal: A exhausting its limit does not limit B.
- Agent and MCP: B's agent `retrieve` tool can't see A's docs. MCP without a token → 401.
- A revoked key is refused right after revocation.

## Hosted migration (written into `report.md` as steps for a human)
1. Create the app role on Neon with a generated password, then GRANT.
2. Set `MIGRATION_DATABASE_URL` (owner) and `DATABASE_URL` (app role) on Render.
3. Deploy, so the migration runs.
4. Create the preview tenant key with the admin CLI, and set `PREVIEW_API_KEY` on the UI service.

## Walking skeleton
- **Deferred:** an OAuth login flow (we only verify tokens; the seam is `core/identity/jwt.py`), per-KB ACLs, and key rotation UX.
- **Bounded:** one bypass function only.

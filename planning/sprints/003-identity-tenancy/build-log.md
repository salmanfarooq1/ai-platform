# Sprint 003: Build log

## Plan
1. Deps (PyJWT, cryptography). Settings: MIGRATION_DATABASE_URL, JWT_*, APP_DB_PASSWORD.
2. Migration 0002 (tables, tenant_id, backfill, RLS, auth_lookup_key / auth_touch_key definer functions).
3. Role setup: docker init SQL + shared grant SQL, harness creates gap_app, tests connect as gap_app.
4. core/identity (models, keys, jwt, store), core/database/tenant.py, startup role guard.
5. api/auth.py: AuthMiddleware (sets request.state.principal before the limiters) + authenticate / require_scope dependencies.
6. Tenant-scope data paths: retriever, ingest, lifecycle, docs, analytics, feedback, usage, agent tools, MCP. Delete NAMESPACE_REGISTRY, KB check -> 404 kb_not_found.
7. Caches keyed by tenant. Rate limit by principal, budget by tenant.
8. Admin CLI, nginx envsubst, render.yaml, vite proxy.
9. Tests (unit, integration, e2e), evidence, docs, report.

## Log
- Read the brief, AGENTS.md, STATE, requirements, blueprint, acceptance, FOUNDATION section 3. Baseline: 215 tests passed (Docker Postgres and Redis up, `gap_app` role did not exist yet).
- `poetry add pyjwt cryptography`: poetry re-resolved and also moved `langchain-litellm` 0.7.0 -> 0.5.1 and `pyjwt` 2.13 -> 2.15. All 215 tests still passed. Noted in the report.
- Settings: `MIGRATION_DATABASE_URL`, `JWT_*` with validation (one key source, secret 32+ chars, issuer and audience required). Local default `DATABASE_URL` is now `gap_app`; `migration_dsn` falls back to the owner role locally and to `DATABASE_URL` elsewhere. Alembic env uses `migration_dsn`.
- Migration 0002 written. Decision: `principals` and `api_keys` get ENABLE but not FORCE row-level security, and `tenants` gets a select-only policy without FORCE. With FORCE, the SECURITY DEFINER lookup functions (owned by a non-BYPASSRLS owner role) would read zero rows before a tenant is known, so key lookup would break. The app role is subject to RLS on all of them. Recorded in the report and ARCHITECTURE.
- Migration also grants `gap_app` its DML rights when that role already exists (role creation stays out of the migration). `scripts/admin/grant_app_role.sql` covers a differently named role.
- Compose: `docker/postgres-init/01-app-role.sh` creates the role on a fresh volume; ran it by hand on the existing volume. `docker-compose.prod.yml` takes `APP_DB_PASSWORD`.
- Built identity core, tenant connection, startup guard (in `create_pool`, closes the pool on refusal), `AuthMiddleware` (before the limiters) plus `require_scope` / `require_kb` dependencies.
- Broke: ingest returned 500, "COPY FROM not supported with row-level security". Fix: `bulk_insert` uses pipelined `executemany` INSERT.
- Broke: MCP tools saw no principal inside an SSE session. The SDK runs each message in the context of the POST that carried it, not of the SSE opener. Fix: a `MessagesApp` wrapper binds the principal from the verified POST request; `AuthMiddleware` also sets `scope["user"]` so the SDK binds each session to the principal that opened it (another principal gets 404 on that session).
- Broke: `parse_key` accepted a trailing newline (`$` anchor). Fix: `fullmatch`. Regression case added.
- Broke: FastAPI 0.137 route tree has no flat `APIRoute` list, so the "no route takes tenant_id" test reads the OpenAPI contract instead.
- Tests: existing e2e and integration fixtures now authenticate and connect as `gap_app`; `owner_pool` / `pool` fixtures (superuser) only verify. Migration tests that meant "the baseline" now migrate to `0001` explicitly. Four tests changed expectation on purpose (rate-limit message wording, budget key, empty-namespace test uses an existing KB, registry gone from config).
- Evidence captured with live runs against a throwaway database; the live server uses the test fakes for LLM and embeddings (no keys exist).
- `rm -rf` of stale `__pycache__` directories was refused by the permission system; not retried. The NAMESPACE_REGISTRY grep is clean without it.
- Architect follow-ups: (1) migration 0003 adds `auth_lookup_principal(principal_id, tenant_id)`; JWT must name an existing, enabled principal of the token's tenant, kind from the database; non-UUID `sub` is rejected (the old uuid5 mapping is gone). (2) `langchain-litellm` pinned `>=0.7.0,<0.8.0`, locked at 0.7.2; pyjwt 2.15.1 and cryptography 50.0.2 kept. `poetry lock` also left litellm at 1.103.2 and langchain-core at 1.6.6 from an intermediate `poetry update`. (3) `audit_db.py`, `clear_legal.py` are tenant-scoped via `CORPUS_TENANT_ID` and `tenant_connection`; `apply_hnsw_index.py` uses `MIGRATION_DATABASE_URL`. Smoke output in `evidence/corpus-scripts.txt`.
- QA round: migration 0004 (revoke write on api_keys, principals, tenants, knowledge_bases; drop default privileges; grant_app_role.sql aligned), MCP per-tool scopes, generic ingest errors, agent retrieve KB check, README lines updated.

# Sprint 003: Report

The Builder returned this report as text, because subagents can't write report files. The Architect saved it here.

## 1. Acceptance
| Check | Status | Evidence |
|---|---|---|
| A1 ruff, mypy, unit | done | `ruff.txt`, `mypy.txt` (69 files), `pytest-unit.txt` (268 passed), `ddl-check.txt` |
| A2 int+e2e as `gap_app` | done | `pytest-int-e2e.txt` (221 passed, 0 skipped) |
| A3 requirement → tests | done | §1b below |
| A4 RLS via psql | done | `rls-psql.txt` |
| A5 startup guard | done | `startup-guard.txt` |
| A6 0001→0002 on existing data | done | `migrate-existing.txt` |
| A7 live curl, two tenants | done | `live-curl.txt` (fakes for LLM and embeddings, real DB, Redis and app) |
| A8 admin CLI | done | `admin-cli.txt` |
| A9 no registry, no tenant from input | done | `grep-tenant.txt` |
| A10 UI build, nginx header from env | done, with a caveat: nginx did not render the template, because image builds are blocked here | `ui-build.txt`, `ui-dist-grep.txt` |
| A11 secrets, docs, hosted steps | done | `secrets-grep.txt`, §8 |

## 3. Tests
Before: 215. After: **492 passed, 0 failed, 0 skipped** (unit 271, int+e2e 221). The Architect re-ran this.

## 4. Notable fixes found while building
- `COPY` is refused under RLS, so `bulk_insert` now uses a pipelined INSERT.
- MCP messages now bind the principal from the verified POST, and a session can't be driven by another principal.
- `parse_key` accepted a trailing newline. It now uses `fullmatch`.
- The pre-sprint semantic cache index is dropped and recreated with a `tenant_id` tag.

## 5. Skipped
- B8: image builds (sandbox).
- B9: Neon and Render steps (human).
- B10: JWT principal lookup. Fixed by migration 0003 and `confirm_jwt_principal`, with tests.
- B11: offline corpus scripts. Fixed, see `evidence/corpus-scripts.txt`.

## 6. Decisions
- FORCE RLS on the 5 data tables. ENABLE only on `principals`, `api_keys` and `tenants`, so the `SECURITY DEFINER` key lookup works. The app role is subject to RLS on all of them.
- The startup guard lives in `create_pool()`.
- Authentication runs as middleware, and routes declare their scopes.
- The preview key's scopes are `query`, `kb:read` and `agent`. The UI's Ask page needs `agent`.
- `kb_not_found` gives the same body for a foreign KB and a missing one.

## 8. Hosted migration steps (human)
Back up Neon first.
1. As the owner role, run `CREATE ROLE gap_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '<generated>'; GRANT CONNECT ON DATABASE <db> TO gap_app;`
2. On Render, set `MIGRATION_DATABASE_URL` to the owner URL and `DATABASE_URL` to the `gap_app` URL.
3. Deploy. Migrations 0002–0004 run. 0002 backfills the existing rows to the tenant `default`.
4. Run `scripts/admin/identity.py create-principal default service ui-preview`, then `create-key <id> --scopes query kb:read agent`. The key is shown once.
5. Set `PREVIEW_API_KEY` on the UI service and redeploy.
6. Check that `/v1/documents` gives 401 without a key and 200 with one.

Commit commands: see the Architect's final summary.

## 1b. Requirement → tests
| Req | Test files (named tests are listed in each file's docstring and in `build-log.md`) |
|---|---|
| 1 Tables, migrations, backfill | `integration/test_migrations.py`, `integration/test_admin_cli.py` |
| 2 RLS and least privilege | `integration/test_rls.py`, `integration/test_app_role_privileges.py` (17 tests, including the QA M1 attack) |
| 3 `tenant_connection` | `unit/test_tenant_connection.py`, two pooled-connection tests in `test_rls.py` |
| 4 Non-privileged role and startup guard | `integration/test_startup_guard.py`, `e2e/test_startup_guard_e2e.py`, `test_rls.py::test_isolation_checks_only_mean_something_as_the_app_role` |
| 5 Authentication | `unit/test_identity_keys.py`, `unit/test_jwt.py`, `integration/test_identity_store.py`, `e2e/test_tenancy.py` (JWT, key, spoof and fail-closed tests) |
| 6 Authorization | `unit/test_auth.py`, `e2e/test_tenancy.py` (scope matrix, identical 404s, A/B isolation), the ingest no-leak test |
| 7 Rate limit and budget | `e2e/test_tenancy.py`, `e2e/test_errors_and_headers.py` |
| 8 MCP | `e2e/test_tenancy.py` (SSE session binding and per-tool scopes), `unit/test_mcp_tools.py`, `e2e/test_mcp.py` |
| 9 Admin CLI | `integration/test_admin_cli.py` |
| 10 Preview key in nginx | `unit/test_ui_proxy_config.py` |
| 11 Caches | `unit/test_cache_keys.py`, `integration/test_cache_tenancy.py`, `e2e/test_tenancy.py` cache tests, agent tool isolation tests |

## QA follow-ups closed
- **M1:** migration 0004. The app role is read-only on the identity tables and has no access to `alembic_version` or any default grants. The Architect re-ran the attack, and the result was `permission denied for table api_keys`.
- **L1:** MCP per-tool scopes. **L4:** README. **L5:** no exception text in ingest error bodies. **L9:** the agent tool checks the KB.
- **M2:** moved to Sprint 004 (fail closed in `enforce()`).
- **L3, L6, L7:** recorded in `planning/RISKS.md`.

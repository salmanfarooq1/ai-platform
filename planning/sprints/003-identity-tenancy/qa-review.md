# Sprint 003: QA and code review

Reviewer: QA (no product code or tests edited, nothing committed). Stack: `docker compose up -d postgres redis`, migration head 0003.
All evidence is captured command output in `evidence/qa-*.txt`. Image builds are blocked in this sandbox, so anything that needs one is "not verified".

## Acceptance A1-A11

| Check | Result | Evidence and notes |
|---|---|---|
| A1 ruff, mypy, unit | pass | `qa-ruff.txt` (clean), `qa-mypy.txt` (69 files, no issues), `qa-pytest-unit.txt` (268 passed), `qa-ddl.txt` (no DDL outside migrations/) |
| A2 int + e2e as `gap_app`, 0 failed, 0 skipped | pass | `qa-pytest-int-e2e.txt`: 204 passed, no skips. `gap_app` shown NOSUPERUSER NOBYPASSRLS in `qa-rls-admin-cli.txt`. `report.md` still says 196 (stale, finding L2) |
| A3 requirement to test table in `report.md` | fail | `report.md` has no table; row A3 points at a "builder hand-back §1b" that is not in the repo (finding M3). The tests themselves exist and are substantive (49 e2e tenancy tests, 15 RLS, 16 JWT, 14 auth, 13 identity store) |
| A4 RLS via psql | pass | `qa-rls-admin-cli.txt`: as `gap_app` with no `app.tenant_id`, all 8 tables count 0. Owner sees rows. FORCE on the 5 data tables, policies listed |
| A5 startup guard | pass | `qa-startup-guard.txt`: superuser in local and prod, and a non-superuser BYPASSRLS role, each exit 3 with the clear `UnsafeDatabaseRoleError` message and no "startup complete" |
| A6 migrate 0001-era data | pass | `qa-migrate-existing.txt`: counts 6/3/3/1 unchanged, one `default` tenant, `tenant_id` backfilled and NOT NULL, 3 KBs seeded, FTS intact, readable by the default tenant as `gap_app`, head = 0003 |
| A7 live curl, two tenants | pass | `qa-attacks.txt`, `qa-attacks-mcp.txt`, `qa-attacks-jwt.txt` (76 curl attempts, 22 MCP, 16 JWT, plus rate limit and raw SQL). No isolation break found |
| A8 admin CLI, hash only | pass | `qa-rls-admin-cli.txt`: tenant, principal, key created, secret printed once, stored value is a 64-char SHA-256 (`hash_matches = t`), secret and token absent from the row and from a full `pg_dump`, revoke works. Exit code of a second revoke was not re-captured here (builder's `admin-cli.txt` shows exit 1) |
| A9 no registry, no tenant from input | pass | `qa-grep-tenant.txt`: `NAMESPACE_REGISTRY` no match. No route, header, query or body reads a tenant. Live spoof tests confirm it |
| A10 UI build, nginx header from env, no key in dist | partly verified | Build passes and no key or `Bearer` string in `ui/dist` or `ui/src` (`qa-ui-build.txt`, `qa-ui-dist-grep.txt`). The require-key entrypoint script exits 1 without the variable (`qa-ui-nginx.txt`). **Not verified:** the rendered nginx config and the Docker image (no nginx, envsubst or image build here) |
| A11 secrets, docs, hosted steps | pass with gaps | `qa-secrets-grep.txt`: no real secret in 301 changed or new files (only dummy `gap_abcd1234_aaaa...` test strings). AGENTS, README, ARCHITECTURE, CHANGELOG, STATE and `render-deployment.md` are updated. `report.md` holds the hosted steps but no proposed commits (M3) and README still has stale lab text (L4) |

## Isolation attacks (extra check)
Details in `evidence/qa-attacks.txt`, `qa-attacks-mcp.txt`, `qa-attacks-jwt.txt`. Every attempt was refused or returned only the caller's own data.
- No or bad credential on every route, MCP SSE and MCP messages: 401. Empty bearer, Basic scheme, truncated key, wrong secret with right prefix, key in the query string, JWT `alg=none`: 401.
- Path tricks (`//v1/...`, `/V1`, `/v1/./`, `/v1/../`, encoded `%76%31`, old unversioned paths): 401 or 404, never data.
- Spoofing as tenant B: `X-Tenant-ID`, `X-Tenant`, `X-Forwarded-User`, `X-Principal-ID`, `?tenant_id=`, body `tenant_id`, form `tenant_id`: ignored. The owner view shows B's writes stayed under B.
- Foreign KB slug: `kb_not_found` body is identical to a missing slug (same body but request_id). Also for ingest, agent and MCP. SQL-ish, wildcard and wrong-case slugs: same 404.
- Same slug `legal` in both tenants: each only sees its own document. B cannot find A's text, A cannot find B's.
- Cache replay: A's exact HIT and semantic HIT are not served to B (B gets its own 404/miss). Redis keys are `cache:v2:*` and each `semcache:*` hash carries its `tenant_id`. The KB check runs before the cache, so B cannot replay A's query against A's KB.
- MCP: no token 401. Key without `query` scope 403. B posting into A's SSE session: 404 and nothing delivered. No-auth and bogus-key POST into a live session: 401. Tools and resources return only the caller's tenant. An extra `tenant_id` tool argument is ignored.
- JWT (server with `JWT_SECRET`): valid token 200. Wrong tenant claim, other tenant's principal, non-UUID or unknown `sub`, expired, wrong `aud`, wrong `iss`, no `exp`, wrong key, `alg=none`, `HS512`: 401. Disabled principal: 401, re-enabled: 200. Migration 0003 works.
- Revocation and disable are immediate (no auth cache).
- Rate limit: per principal. B hit 429 after 60 requests, A was unaffected, and spoofed `X-Forwarded-For` / `X-Real-IP` did not evade it. Trailing-slash and double-slash variants do not evade it.
- Raw SQL as `gap_app` in tenant A context: cannot read, write or update tenant B rows, no setting gives 0 rows. See finding M1 for what it can do inside its own tenant.

## Findings

### High
None. No isolation break, no secret, no weakened or skipped test found.

### Medium
- **M1. The app role can edit its own tenant's keys, principals and knowledge bases.** `migrations/versions/0002_identity_tenancy.py:129,133` grants SELECT/INSERT/UPDATE/DELETE on all tables, and the policy is `FOR ALL`. Live: as `gap_app` in tenant A, `UPDATE api_keys SET scopes='{admin}', revoked_at=null` hit 3 rows and `INSERT INTO knowledge_bases` succeeded (`qa-attacks.txt`, section 12). An SQL-injection or code bug could escalate scopes or un-revoke a key. Fix: new migration 0004 that revokes INSERT/UPDATE/DELETE on `api_keys`, `principals`, `tenants` and `knowledge_bases` from `gap_app` (the app only reads them; key `last_used_at` goes through `auth_touch_key`), and change the default privileges so new tables do not auto-grant DELETE.
- **M2. Rate limit and token budget fail open when Redis errors.** `api/middleware/rate_limit.py:97` and `api/middleware/token_budget.py:84` log and allow the request. Strict rule 3 says fail closed for budget. This predates the sprint but the sprint re-keyed both. Fix: return 503 `service_unavailable` on a Redis error for the budget check (and for the limiter in `public-preview` and `prod`), or record it in `planning/QUESTIONS.md` and DECISIONS.md as a deliberate exception until Sprint 004 moves them into `enforce()`.
- **M3. `report.md` is incomplete against the completion standard.** No requirement-to-test table (A3), and the A3 row points at a hand-back that is not in the repo. No proposed commit commands ("see the Architect's final summary"), which AGENTS.md requires in `report.md`. Section numbers skip 2 and 7. Fix: add the table (requirement 1-11 to test file and name) and the commit commands to `report.md`.

### Low
- **L1. Scope gap between MCP and REST.** `api/middleware/auth.py:81` checks only `query` for all MCP traffic, so a query-only key can call `get_cost_summary`, `get_ingestion_status` and read `rag://documents/...`, which REST gates behind `kb:read`. It stays inside the tenant. Fix: map each MCP tool and resource to the same scope as its REST twin.
- **L2. `report.md` evidence count is stale.** Row A2 says 196 passed; `evidence/pytest-int-e2e.txt` and this run show 204. Fix: edit the row to 204.
- **L3. JWT scopes come from the token, including `admin`.** `core/identity/jwt.py:92-101` trusts the issuer for scopes. This is normal for OAuth tokens but means a compromised issuer key is a full-tenant key. Fix: document it in `docs/ARCHITECTURE.md`, or intersect token scopes with a per-principal maximum in a later sprint.
- **L4. Stale README text.** `README.md:264` (rate limit "per namespace"), `:286` (`budget:{namespace}:{date}`, now `budget:{tenant}:{date}`) and `:322` ("Namespace registry"). Fix: add a short "superseded in Sprint 003" note or update the three lines.
- **L5. Ingest returns raw exception text.** `api/routers/ingest.py:101` returns `str(e)` in a 500 body (also `:99` for the 415). It can show internals to a tenant. Fix: log it and return a generic message with the request id.
- **L6. Migration 0002 drops indexes** (`:86-91`) on a live hosted table. FOUNDATION section 6 asks for additive-first changes. The replacements are created in the same migration, so the risk is a short lock. Fix: note it in the hosted steps, or create the new indexes first and drop the old ones in 0004.
- **L7. Preview key is shared by all public visitors.** One principal means one 60/min limit and one tenant budget for everyone, so a single visitor can exhaust both. This is by design for the preview. Fix: record it as a known limitation in `planning/RISKS.md`.
- **L8. Working tree mixes sprints 000-003.** `git diff` shows the UI rebrand, `test_llm.py` and `test_finops.py` rewrites and the Dockerfile change from earlier sprints, so a pure Sprint 003 review of the diff is not possible. The test rewrites there are justified in their own docstrings and CHANGELOG (Sprint 002). Fix: commit per sprint branch as `report.md` proposes.
- **L9. Agent tool `namespace` is model-controlled and not checked against the tenant's KBs** (`api/agent/tools.py`, `retrieve_chunks`). Row-level security and the tenant filter bound it, so it is only an empty result for a foreign slug. Fix: reuse `require_kb` in the tool for the same error body.

### Checked and clean
- No `skip`, `xfail` or `skipif` in tests except the three documented "service unreachable" skips in `tests/harness.py:75,88,90` (0 skipped in this run). No deleted real tests (two placeholder files only). The `type: ignore` and `noqa` comments in the new code carry a reason or are the standard side-effect and `E402` import cases.
- Fakes: `tests/conftest.py` blocks litellm entry points and non-loopback sockets for every test; `tests/fakes.py` makes no network call.
- No placeholder DSNs in product code. The only literal DSNs are the documented local defaults in `core/settings.py:20-21` and `scripts/setup_db.sh:13`. `docker-compose.prod.yml` requires both passwords.
- Tests assert bodies, headers, row ownership and cache keys, not only status codes (sampled `tests/e2e/test_tenancy.py`).

## Not verified
- nginx rendering of `ui/nginx.conf` and the UI Docker image (A10), and the `Dockerfile` migrate-then-start command: image builds are blocked.
- Hosted steps in `report.md` section 8 against Neon and Render (human steps).
- JWT with `JWT_JWKS_URL` (only the `JWT_SECRET` path was run live).
- A repeat of `revoke-key` exit code (A8) in this run.

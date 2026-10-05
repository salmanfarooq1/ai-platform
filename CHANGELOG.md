# Changelog

One short entry per sprint, newest first. Full detail lives in `planning/sprints/`.

## Sprint 005: frontend foundation and showcase
- **What was built:**
  - **Web edge (ADR-0007):**
    - Sign in with an API key. The browser gets an HttpOnly, SameSite=Strict cookie session (Secure outside local) and a CSRF token.
    - The session lives in Redis and never holds the key.
    - A revoked key or a disabled principal ends its sessions.
    - Preview mode starts an automatic read-only session for `PREVIEW_PRINCIPAL_ID` (migration `0006`, `auth_lookup_preview`).
    - Bearer keys and JWTs work as before.
  - **Console API:** read-only, under RLS, and gated by the new scope `audit:read` and action `audit.read`.
    - `GET /v1/decisions` with filters and a cursor, and `/v1/decisions/{id}` with the request trace.
    - `/v1/policies` and `/v1/policies/{version}`.
    - `/v1/principals`, with no secrets.
    - `/v1/usage/summary`.
  - **New UI** (`ui/`): React and Vite in strict TypeScript, Tailwind with hand-built shadcn-pattern components on Radix, a typed client generated from `docs/openapi.json`, and TanStack Query.
    - Workspace: Ask, Library and History.
    - Governance: Decisions explorer, Policies, Keys, Usage and Agent runs.
    - Also Trust (a placeholder) and System.
    - A public landing page with a GSAP scroll story and a lazy three.js hero.
    - The old JavaScript UI and the nginx preview-key injection are removed.
  - **Design:** the project design skill `.claude/skills/governed-design/` merges apple-design, the MIT taste skill and `docs/UI_GUIDELINES.md` (now 2.0.0).
  - **Tests and CI:** Vitest, Playwright (against the real API with fakes and real Postgres and Redis), axe, and a CI workflow for the frontend.
- **Test delta:** backend 709 before, 805 after (0 skipped). Frontend: 34 Vitest and 36 Playwright tests. Lighthouse desktop performance on the landing page is 99. axe found 0 violations in both themes.
- **QA follow-ups:**
  - M1: crafted cursors give 400.
  - M2: revoking a key ends its cookie session.
  - L1 to L4 are fixed: history is cleared on sign-out, CSRF on sign-out, CI path filters, and session cleanup on failure.
  - M3 (the sign-in limit behind a proxy) is parked as Q12.
- **Not verified here:** the UI Docker image build (npm in the build container), and the CI workflow on GitHub.

## Sprint 004 — gateway core
- **What was built:**
  - `gateway/`: `enforce(ctx, action) -> Decision` with the stages principal, boundary, policy, input guardrails, rate and budget, in that order. Any exception in any stage is a deny (`internal_error`). `require()` raises `GatewayDenied`. Typed actions `kb.read`, `kb.write`, `model.invoke`, `tool.call`, `agent.run`.
  - `ExecutionBoundary`: frozen, built once per request from scopes and the tenant's active policy, and it can only narrow (`narrow()` raises on a widening). The agent and its tools get the boundary, never the raw principal.
  - Policies: migration `0005` adds `policies` (append-only versions, one active per tenant) and `gateway_decisions` (one row per `enforce()` call: SHA-256 of the input, never the text). Row-level security is forced on both, and the grants to `gap_app` are explicit (`policies` SELECT; `gateway_decisions` SELECT and INSERT). Admin CLI: `set-policy <tenant> <file.json>`, `show-policy <tenant>`. No policy means the platform default (what scopes grant).
  - Wiring: search, ingest, documents and agent routes, every agent LLM and tool call, and the MCP tools and resources call the gateway. A deny is 403 `policy_denied` (the reason code is in the message), 400 `query_blocked`, 429 (rate, budget, same codes and headers as before) or 503 `dependency_unavailable`. An agent run cut short by a denial returns a partial answer with `flagged=true` and `flag_reason` (new fields). Tool calls from verifier retries share `max_tool_calls`.
  - `RateLimitMiddleware` and `TokenBudgetMiddleware` are removed; their logic lives in `gateway/limits.py` with the same Redis keys. FinOps books tokens through `gateway.limits.record_usage`.
  - An import-lint test keeps `litellm`, `langchain_litellm` and `asyncpg` out of the agent tools and MCP code. ADR-0006.
- **Behaviour changes to know:** when Redis is down, search, ingest and agent runs now answer 503 `dependency_unavailable` instead of allowing the request. A failed decision write on an allow answers 503 `decision_unrecorded`. Input guardrails run before the rate limiter, so a blocked query no longer uses a rate-limit slot. Opening an MCP session still counts against the rate limit; tools do not. `/v1/documents`, the MCP namespace listing and `list_namespaces` show only the KBs the tenant policy allows.
- **Test delta:** 492 passed before, 709 after (unit 424, integration and e2e 285, 0 skipped). Existing tests changed only in fixtures and expectations listed in `planning/sprints/004-gateway-core/report.md`; the Sprint 003 rate and budget tests are unchanged except one import line.
- **QA follow-ups:** M1 to M4 and L1 to L4 were fixed, and N1 was fixed by the Architect.
  - M1: MCP gates `tool.call` and `model.invoke`, not only `kb.read`.
  - M2: a failed decision write on an allow gives 503 `decision_unrecorded` (decision writes fail closed, ADR-0006).
  - M3: `/v1/config` lists only the KBs the policy allows.
  - M4: new actions `feedback.write` and `analytics.read` cover feedback, quality-report and analytics.
  - L1: an AST check proves every agent tool, MCP tool and MCP resource calls the gate, and `graph.py` is in the import guard. L2: scope denials write a deny row. L3: completion tokens count against `max_tokens_per_request`. L4: no verifier call after a halt.
  - N1: `multi_namespace_search` with explicit namespaces now runs its own `tool.call` check, with a new e2e test.
- **Known limitations:** retention of `gateway_decisions` is undefined (Q7), the accepted lows N2, N3, N5 to N9 are in `planning/RISKS.md`, the image build was not run in the sandbox (B11), and the `hypothesis` dev dependency is new.

## Sprint 003 — identity and tenancy
- **What was built:**
  - Authentication: every `/v1` route except `/v1/health` needs `Authorization: Bearer <API key or JWT>`. API keys are `gap_<prefix>_<secret>` (only a SHA-256 hash is stored, compared in constant time). JWTs are verified against `JWT_JWKS_URL` or `JWT_SECRET` with issuer and audience checked and `alg=none` and HS/RS confusion rejected. The token's `sub` must be the UUID of an existing, non-disabled principal whose tenant equals the token's `tenant_id` claim (migration `0003`, function `auth_lookup_principal`), otherwise 401; the principal kind comes from the database. The tenant comes only from the verified credential.
  - Authorization: scopes `kb:read`, `kb:write`, `query`, `agent`, `admin`, declared per route. 401 for a missing or bad credential, 403 for a missing scope, 404 `kb_not_found` for an unknown or foreign knowledge base (same body for both).
  - Migrations `0002`, `0003` (one lookup function) and `0004` (least privilege: `gap_app` can no longer INSERT, UPDATE or DELETE `api_keys`, `principals`, `tenants` or `knowledge_bases`, and future tables get no automatic grant): `tenants`, `principals`, `api_keys`, `knowledge_bases`; `tenant_id` on `documents`, `document_registry`, `usage_log`, `feedback`; existing rows backfilled to a `default` tenant that owns `legal`, `kyc_aml` and `default`; row-level security on every tenant-owned table. `NAMESPACE_REGISTRY` is gone.
  - `tenant_connection(pool, tenant_id)` sets `app.tenant_id` per transaction; all request-path queries use it. The app connects as the non-privileged role `gap_app` and refuses to start as a superuser or `BYPASSRLS` role (`MIGRATION_DATABASE_URL` is the owner role for Alembic and the admin CLI).
  - Caches (exact and semantic) are keyed by tenant. The rate limit is per principal, the daily token budget per tenant. MCP needs the same bearer credential and runs as the caller's tenant. The agent carries the tenant in its run config, not in a tool argument.
  - Admin CLI `scripts/admin/identity.py`: create tenant, knowledge base, principal and key (secret shown once), revoke and list keys.
  - UI: nginx adds the preview key (`PREVIEW_API_KEY`, a Render secret) to `/api/` calls server-side; the Vite dev proxy does the same from `ui/.env.local`.
- **Behaviour changes to know:** bulk ingest uses a pipelined INSERT instead of `COPY` (Postgres refuses `COPY FROM` into a table with row-level security). The semantic-cache index is recreated on startup if it lacks the `tenant_id` field, and `CACHE_SCHEMA_VERSION` is 2, so old cache entries are not served. Rate-limit and budget keys changed (per principal, per tenant), so counters start fresh. The old `namespace` request parameter now names a knowledge base owned by the caller. `/v1/config` lists only the caller's knowledge bases.
- **Test delta:** 215 passed before, 472 after (unit 268, integration and e2e 204). Existing tests were updated to authenticate and to run as `gap_app`; no assertion was loosened. Seven tests and four migration tests changed their expectation because the behaviour they pinned was replaced on purpose (listed in `planning/sprints/003-identity-tenancy/report.md`, section 4).
- **QA fixes:** MCP tools and resources check the scope of their REST twin (search: `query`; ingestion status, cost summary, namespaces, resources: `kb:read`); ingest 415/500 bodies are generic (detail goes to the log); the agent retrieve tool checks the namespace against the tenant's knowledge bases (`kb_not_found`).
- **Offline scripts:** the corpus ingest, `audit_db.py`, `clear_legal.py` and the eval lab take `CORPUS_TENANT_ID` and run through `tenant_connection`; `apply_hnsw_index.py` is admin DDL and uses `MIGRATION_DATABASE_URL`.
- **Known limitations:** one `last_used_at` write per authenticated request. Hosted rollout steps are in `docs/render-deployment.md` and need a human (Neon role, Render secrets).

## Sprint 002 — platform base
- **What was built:**
  - Validated settings (`core/settings.py`, pydantic-settings). Startup fails fast on a bad `MODE` or on `public-preview`/`prod` without `DATABASE_URL` and `REDIS_URL`. Placeholder DSNs are gone.
  - Alembic migrations (`migrations/`). Baseline `0001` is idempotent and safe on the hosted database. `core/database/schema.sql` is deleted. The Docker image runs `alembic upgrade head` before uvicorn.
  - `/v1` API versioning. `/` and `/health` stay unversioned. MCP moved to `/v1/mcp/sse`. UI and `claude_desktop_config.json` updated.
  - One error format, `{"error": {"code", "message", "request_id"}}`, for every error including 429s and 500s.
  - JSON logs with `request_id` and `trace_id`, OpenTelemetry FastAPI spans (no exporter unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set), `X-Request-ID` and `X-Trace-ID` on every response.
  - mypy (passing) and a clean `ruff check` (was 33 errors).
  - Real integration and e2e test tiers (Postgres + Redis, fake LLM and embeddings), a network guard, and CI jobs for lint, mypy, unit, integration+e2e and a migration check.
- **Fixes found on the way:** the MCP SSE endpoint used `mcp._mcp_server`, which does not exist in MCP SDK 2.x, so connecting failed. It now uses `_lowlevel_server` and is a raw ASGI route.
- **Pre-existing test failures:** B1 (`test_llm.py` tested a function removed on purpose, rewritten against `generate_with_citations`) and B2 (tests expected a groq pricing entry the config no longer uses; tests now follow the configured models, and the Gemini model has a $0 free-tier entry).
- **Test delta:** unit 149 passed (the baseline did not collect: B1). Integration and e2e: 66 passed, 0 skipped. Full run: 215 passed.
- **Also fixed:** ingested chunks now store the real upload filename (`source_filename`), and `/v1/search` usage rows carry the real model, so cost is priced and logged.
- **Known limitations:** chunks ingested before this sprint still cite `unknown` until re-ingested, and old `/search` usage rows keep `model="unknown"`. Usage rows written before this sprint carry the old `/search` style endpoint names.

## Sprint 000 — operating structure, functional naming
- **What was built:**
  - `AGENTS.md` and its pointer files (`CLAUDE.md`, `CODEX.md`), `CONTRIBUTING.md`, and the `planning/` folder.
  - The ADR index and template, the PR template, `.editorconfig`, `.gitattributes`, and `.claude/settings.json`.
- **Renames and moves:**
  - The mode `demo` is now `public-preview`, and an unknown `MODE` now fails at startup.
  - The old product name is removed. `BRANDING.md` moved to `docs/UI_GUIDELINES.md`, and `ARCHITECTURE.md` moved to `docs/ARCHITECTURE.md`.
- **Decisions:** see `planning/DECISIONS.md`, Sprint 000 lines.
- **Test delta:** added `tests/unit/test_config_mode.py`.
- **Known limitations:**
  - There were 33 lint errors on `main` before this sprint, and they are not fixed here (Q3).
  - The hosted service needs `MODE=public-preview` set (Q2).

## Before Sprint 000
- **What exists:** the labs and the platform built before the sprints, recorded in the numbered sections of `README.md` (sections 1 to 12) and in Decisions 1 to 23 of `docs/ARCHITECTURE.md`.
- **Where the detail is:** `git log` holds the commit history (labs, retrieval, caching, the agent, the MCP server, cost tracking, the Render deploy and the UI).

# Changelog

One short entry per sprint, newest first. Full detail lives in `planning/sprints/`.

## Sprint 008: trust baseline
- **What was built:**
  - **Receipts and a hash chain (migration `0009`, ADR-0012).** Each decision row links to the one before it per tenant. `GET /v1/receipts/{id}` returns an Ed25519 signed receipt, `GET /v1/receipts/keys` the public keys, `POST /v1/receipts/verify` the same checks as the offline `scripts/verify/receipt.py`. `RECEIPT_SIGNING_KEY` is required outside local mode.
  - **Retention (Q7).** 90 days by default, per-tenant override, a `purge_decisions` job through a narrow SECURITY DEFINER function, a daily scheduler in the worker, and a chain checkpoint so verification survives a purge.
  - **Eval gate.** `scripts/eval/run_gate.py` runs a fixed suite with the fake LLM against a stored baseline and fails CI on a regression. `run_real.py` is manual.
  - **Cost breaker.** A `cost` gateway stage: over the daily cap gives 429 `cost_cap_exceeded`; Redis down denies.
  - **Metrics.** `/metrics` in Prometheus format, an `observability` compose profile with Prometheus and a provisioned Grafana dashboard.
  - **UI.** The Trust page verifies receipts, shows retention and the eval gate history. The decision panel has "Verify receipt".
- **API change:** new `/v1/receipts/*`, `/v1/trust/summary`, `/metrics`. Settings: `RECEIPT_SIGNING_KEY` (required in `public-preview` and `prod`), `DECISION_RETENTION_DAYS`, `DAILY_COST_CAP_USD`, `METRICS_PUBLIC`.
- **QA fixes:** purge checkpoints are signed and only the purge function writes them (`gap_app` lost INSERT on `chain_checkpoints`); a 30-day floor on retention in the function; an unpriced model costs the highest known rate and hosted modes refuse to start for an unpriced model; unknown HTTP methods share one `OTHER` metric label; `RECEIPT_SIGNING_KEY` is a `SecretStr`; the Trust page shows only signed fields as Verified. Migration `0009` was changed in place (not released).
- **Test delta:** backend 1188 → 1294 (10 live-MinIO skips), Vitest 182 → 192, Playwright 72 → 77.
- **Not verified here:** CI on GitHub, the hosted (Neon) migration, a real provider run, a Docker image build.

## Sprint 007: durable jobs, the outbox and raw storage
- **What was built:**
  - **Job queue (migration `0008`, ADR-0011).** A `jobs` table with forced row-level security. Workers claim with `FOR UPDATE SKIP LOCKED` through a narrow SECURITY DEFINER function, hold a lease, retry with backoff and end `dead` after the last attempt. An idempotency key is unique per tenant. `python -m workers` handles SIGTERM, writes a health file and logs a line per job. `docker compose` has a `worker` service.
  - **Outbox (ADR-0008 updated).** Events are written in the transaction of the change and a relay publishes them at least once. The Postgres outbox bus passes the EventBus contract suite. `IdempotentConsumer` dedupes by CloudEvent id, in memory and in `processed_events`. It is the default bus. The M1 rule holds: a decision row is never lost because of the bus.
  - **Ingestion in a worker.** `POST /v1/ingest` stores the raw bytes by SHA-256 (once) and answers 202 with a job. The worker chunks, embeds, reports progress per batch and writes `platform.ingest.completed.v1`.
  - **Agent runs in a worker.** `JobAgentRuntime` is the second `AgentRuntime`. `/v1/agent/query` keeps its synchronous contract and answers 202 `{execution_id, job_id}` after `AGENT_SYNC_WAIT_SECONDS`. Run status is durable (Q19 closed).
  - **UI.** The Library shows each document's job status and progress (polled every 2 s only while a job is active). The Agent runs page reads `/v1/agent/runs` and shows status and duration. Ask in Agent mode shows a quiet "Still working" state for a slow run.
- **API change:** `POST /v1/ingest` is 202 `{job_id, status}` (200 for a repeated `Idempotency-Key`), not the old ingest result. New: `GET /v1/jobs`, `GET /v1/jobs/{id}`, `GET /v1/agent/runs`, `GET /v1/agent/runs/{execution_id}`, `execution_id` filter on `/v1/decisions`. `POST /v1/agent/query` may answer 202.
- **QA fixes:** run and job routes show only runs in knowledge bases the caller's policy allows, and without `audit:read` only the caller's own runs (new `jobs.principal_id` and `jobs.namespace`). Agent usage is booked at most once per `execution_id`. The payload cap follows the question's `max_query_length`. Failed runs return the code `agent_run_failed`, never the exception text. The question text is no longer logged. An unreadable claimed job is released at once.
- **Test delta:**
  - Backend: 1097 before, 1188 after, 10 skipped (the live MinIO run only).
  - Frontend: 182 Vitest tests (167 before) and 72 Playwright tests (71 before).
- **Not verified here:** the live MinIO run, the hosted migration (non-superuser owner tested locally only), CI on GitHub, a Docker image build and a run of the compose `worker` service, and any real provider.

## Sprint 006: ports and adapters, event bus, agent runtime
- **What was built:**
  - **Ports and adapters (ADR-0005 updated).**
    - `ports/` holds typed Protocols for the LLM, the agent's chat model, embeddings, the knowledge store, the cache, the object store, the event bus and the agent runtime.
    - `adapters/` implements them: LiteLLM, Postgres with pgvector, Redis, local disk and S3, and the in-process bus and runtime.
    - `adapters/registry.py` builds one bundle from settings in the lifespan. Routes, the gateway, the agent and MCP get ports, never SDKs.
    - Only `adapters/` imports `litellm`, `langchain_litellm`, `boto3` or `redis`. `asyncpg` is allowed only in `adapters/`, `core/database/` and `core/identity/store.py`. Import-lint tests fail on an injected violation of each.
    - mypy is strict on `ports/` and `adapters/`.
  - **Embedding provenance (migration `0007`).** Chunks record `embedding_model` and `embedding_dim` (backfilled from the configured model, then not null). Search, text and vector, reads only the active model. Other chunks are ignored and counted in `/v1/health` as `stale_vectors`. The response caches carry the model too.
  - **Embedding fallback.** `EMBED_FALLBACK_MODELS` is an ordered list. A provider with another vector width is refused and logged.
  - **Event bus (ADR-0008).** CloudEvents 1.0. The gateway publishes `platform.gateway.decision.v1` for every recorded decision, inside the decision's transaction, with no input text.
  - **Agent runtime (ADR-0009).** `/v1/agent/query` runs through `start`, `wait` and `cleanup`. Every decision a run causes carries its `execution_id` (nullable column in `0007`). A stop also cancels a tool call in flight.
  - **UI.** The Agent runs page shows the execution id and the run status from the runtime.
  - **Tests:** contract suites for every port in `tests/contracts/`. The fakes are adapters behind the same ports, and the test app is built by the registry.
- **API change:** `/v1/health` gains `stale_vectors`. Console decisions gain `execution_id` and `run_status`. Nothing else visible to clients changed.
- **Test delta:**
  - Backend: 875 before, 1084 after, 10 skipped (the live MinIO run only). Unit 543, integration, e2e and contracts 541.
  - Frontend: 167 Vitest tests (162 before) and 71 Playwright tests (70 before).
- **Not verified here:** the live MinIO run (image not pullable; `scripts/verify/minio.sh`), the hosted migration, CI on GitHub, and any real provider (the live stale-vector run used fakes behind the ports).

## Sprint 006: ports and adapters, event bus, agent runtime
- **What was built:**
  - **Ports and adapters.** Typed ports in `ports/` for the LLM, chat model, embeddings, knowledge store, cache, object store, event bus and agent runtime. Adapters in `adapters/`, with one composition root (`adapters/registry.py`).
    - `api/`, `core/` and `gateway/` import no provider SDK, and the import-lint tests enforce it.
    - Each port has a shared contract suite, which the fakes and the real adapters both pass.
  - **Embedding provenance (migration 0007).** Every vector records its model and dimension.
    - Search ignores vectors from another model.
    - `/v1/health` reports `stale_vectors`.
    - An embedding fallback list refuses a provider whose dimension differs.
  - **EventBus (ADR-0008).** CloudEvents 1.0 events, with an in-process adapter. Every recorded decision publishes `platform.gateway.decision.v1`, which holds no input text.
    - An allow whose publish fails is denied with 503.
    - A deny keeps its record even if the publish fails.
  - **AgentRuntime (ADR-0009).** It has start, status, wait, stop and cleanup, with an in-process adapter. `/v1/agent/query` runs through it, and every decision of a run carries its `execution_id`. The Agent runs page shows the execution id and status.
- **Test delta:**
  - Backend: 875 before, 1097 after. The 10 skips are the live MinIO run, which isn't available here; run `scripts/verify/minio.sh`.
  - UI: 167 Vitest tests and 71 Playwright tests.
- **Found and fixed:** the API Docker image didn't copy `ports/` and `adapters/`.
- **Open:**
  - Q16: embedding fallback providers.
  - Q17: deploy 0007 with the new image.
  - Q18: the agent cost call always fails.
  - Q19: run status lives in memory until Sprint 007.
  - Q20: the stale-vector count runs on every health check.

## Sprint 005b: polish round
- **What was built:**
  - **Ink-and-paper palette** as DTCG design tokens (`ui/tokens/tokens.json`), built into CSS by Style Dictionary.
    - CI fails if the generated CSS drifts from the tokens.
    - Lint fails on hard-coded colors.
    - The brand blue is gone. ADR-0010 records the decision.
  - **Landing page:** the new copy ("Your agents can only ever do less."), a hero built from real console components with example data, and use cases. A new How it works page.
  - **Console:**
    - An Overview home.
    - Requests with a drawer.
    - Deny emphasis, with the failing stage, a plain sentence, and the policy field and version.
    - Plain-language reasons from `/v1/reason-codes`.
    - A governance line under each answer in Ask.
    - A guided walkthrough with one allowed and one blocked real request.
    - A session menu and a Cmd+K command palette.
    - Route-level code splitting.
  - **API:** `/v1/overview`, `/v1/requests`, `/v1/requests/{id}` and `/v1/reason-codes`. The console's own reads are left out of the counts unless they were denied.
  - **Docs:** a standard design doc set in `docs/design/`. `docs/UI_GUIDELINES.md` is now an index.
- **Test delta:**
  - Backend: 805 before, 875 after, 0 skipped.
  - Frontend: 162 Vitest tests and 70 Playwright tests.
  - Lighthouse on the landing page: desktop 99, mobile 85.
  - axe: 0 violations in both themes.
- **Not verified here:** a human visual review, the UI image build, and CI on GitHub.

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

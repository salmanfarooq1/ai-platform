# Foundation architecture

The base every later layer builds on. It must be strong, stay at $0, and be production-shaped at a small scale. The decisions behind it are in ADRs 0001–0005.

## 1. Gaps found in the code (baseline)
1. **No identity.** The caller supplies its own `namespace` (`api/middleware/rate_limit.py`, `config.py` `NAMESPACE_REGISTRY`).
2. **Tenancy is a free-text `namespace` column.** There is no tenant entity and no row-level security.
3. **No migrations.** The schema is `CREATE TABLE IF NOT EXISTS` in `core/database/schema.sql`, applied by hand.
4. **Ingestion runs inside the request** (`api/routers/ingest.py`). There is no queue, retry or dead-letter queue.
5. **No provider interfaces.** LiteLLM strings are spread across modules, and there is no embedding fallback.
6. **`VECTOR(768)` is fixed,** and no record says which model produced a vector.
7. **No raw-file store and no document versions** (`core/ingestion/lifecycle.py` keeps only the latest hash).
8. **Weak observability:** unstructured logs, no OpenTelemetry (only a flag), no global error handler, no `/v1`.
9. **The agent can call any tool** (`api/agent/graph.py` `ToolNode`), and there is no streaming.
10. **Config is raw `os.getenv` and dicts.** An unknown `MODE` used to fall back silently; this was fixed in Sprint 000.
11. **Testing:** about 63 unit tests, no typecheck, no integration gate in CI, and 33 lint errors on `main`.

## 2. Target architecture
```
            Clients: UI · MCP clients · A2A agents · REST
                               │
  ┌────────────────────────────▼─────────────────────────────┐
  │ GATEWAY  enforce(): authN → tenant → policy → guardrails  │
  │          → budget/rate → route → audit (fail closed)      │
  └────────────────────────────┬─────────────────────────────┘
  ┌──────────── modular monolith, one deploy ─────────────────┐
  │  knowledge          agents            workflows           │
  │  retrieval, KBs     LangGraph,        durable jobs,       │
  │                     tool registry     approvals, DLQ      │
  │              ↘          ↓          ↙                      │
  │  data: ingestion, contracts, lineage, versions            │
  └────────────────────────────┬─────────────────────────────┘
  Postgres (truth: tenants, docs, vectors, queue, receipts, policy data)
  Object storage (raw files by hash) · Redis (derived cache/limits)
  DuckDB (derived analytics, in-process)
  Across all layers, trust: OTel traces · receipts · evals · cost
```
- Modules talk through typed interfaces only (ADR-0001).
- The gateway can become its own service with a deployment change only (ADR-0004).

## 3. Strict rules (do not change)
1. **Identity from a verified token only.** Tenant and principal never come from a header, body or query.
2. **Every tenant-owned row has `tenant_id`, enforced by Postgres row-level security.** No code bypasses it.
3. **Fail closed.** If auth, policy, budget or guardrails error out, the answer is deny.
4. **Governance lives outside the agent.** Every model, tool, data and agent-to-agent call goes through `enforce()`, inside the request's ExecutionBoundary.
5. **Authority only narrows.** Delegated agents and tools never get more permission than their caller.
6. **Postgres is the source of truth.** Caches and analytics are derived and can be rebuilt. Raw files are never changed and are addressed by hash.
7. **Schema changes only through migrations.** These are versioned, forward-only and reviewed.
8. **Contracts first.** Typed Pydantic models, OpenAPI, and `/v1` versioning. A breaking change means a new version.
9. **Open standards over custom:** MCP, A2A, OAuth2/JWT, OpenTelemetry, OPA/Rego, OpenAPI, CloudEvents.
10. **Everything is traceable.** Each request gets a trace ID and a receipt (policy version, prompt version, model route, data versions). The receipt holds hashes, never raw content.
11. **Every side effect is idempotent.** Writes and jobs carry idempotency keys and are safe to retry.
12. **Providers sit behind ports.** Swapping one is a config change. Vectors record the model and dimension that produced them.
13. **Stateless compute.** Any instance can die, and all state lives in stores.
14. **Config and secrets are validated at startup,** and startup fails fast if they are wrong. No secrets in code or logs.
15. **Nothing merges without CI passing:** lint, typecheck, tests, and an eval regression gate.

## 4. Rule → automated check
| Rule | How it is enforced | Sprint |
|---|---|---|
| 1 | Test: a request with a spoofed `namespace` or tenant header gets 401/403. Lint: no route reads tenant from request input. | 003 |
| 2 | Integration test: with tenant A set, queries return no rows from tenant B. Migration check: every table has `tenant_id` and a row-level security policy. | 003 |
| 3 | Unit tests: each `enforce()` stage raising an exception results in deny. | 004 |
| 4 | Import-lint: agent and tool modules cannot import provider or DB modules directly. Test: a tool outside the ExecutionBoundary is refused. | 004 |
| 5 | Property test: the delegated boundary is always a subset of the parent's. | 004 |
| 6 | Test: wipe Redis, and the service still answers correctly. Test: a raw file's hash matches its stored key. | 006 |
| 7 | CI check: `alembic upgrade head` on an empty DB, and no `CREATE TABLE` or `ALTER TABLE` outside `migrations/` (both in 002). The schema diff against the models is deferred to when models exist. | 002 (diff deferred) |
| 8 | CI: the OpenAPI snapshot diff fails on breaking changes. Test: every public route is under `/v1`. | 002 |
| 9 | Review checklist in the PR template. Contract tests for MCP (existing) and A2A (Phase 2). | 002 onward |
| 10 | Test: every response carries a trace ID, and a receipt row exists for each `enforce()` call. | 002 (trace), 007 (receipt) |
| 11 | Test: sending the same job or write twice with one idempotency key gives one effect. | 006 |
| 12 | Import-lint: provider SDKs (`litellm`, `groq`, …) are imported only in `adapters/`. Test: vector rows have a non-null model and dimension. | 005 |
| 13 | Test: kill the API process mid-job, and the job resumes in a worker with no state lost. | 006 |
| 14 | Unit tests: a bad `MODE` or missing required settings fails at startup. Secret scanning in CI. | 000 (mode), 002 |
| 15 | Branch protection: CI is required. The eval gate fails if retrieval or agent scores drop below baseline. | 002, 007 |

## 5. Build order: walking skeletons
Each sprint builds the thinnest correct version, names what is deferred, and leaves a seam.

| Sprint | Thinnest real version | Deferred (bounded) | Seam |
|---|---|---|---|
| 002 Platform base | pydantic-settings, an Alembic baseline equal to the current schema, `/v1` routes (the old paths redirect), one error format, JSON logs, OTel traces to the console or a free collector, mypy on new modules | Metrics dashboards, full mypy coverage | `Settings` object, OTel exporter set by config |
| 003 Identity and tenancy | API keys (hashed in DB) and JWT (HS256 locally, JWKS later) resolve to a principal and a tenant; `tenants` table; `tenant_id` with row-level security; namespaces become knowledge bases with a default tenant backfill | OAuth/SSO, user management UI | An `Authenticator` interface |
| 004 Gateway core | `enforce()` with each stage as a small class; a Python policy engine reading policy rows; budget and rate stages moved from middleware; an ExecutionBoundary on agent tools | OPA/Rego, PII guardrails, approvals | A `PolicyEngine` interface, a stage list in config |
| 005 Ports and adapters | Protocols for LLM, Embedder, VectorStore, ObjectStore and JobQueue; current providers wrapped; model and dim columns on vectors; import-lint | Extra providers, an embedding fallback | Adapter registry by config |
| 006 Durable jobs | A Postgres `SKIP LOCKED` queue (procrastinate or pgqueuer) with retries, a dead-letter table and idempotency keys; ingestion runs in a worker; raw files go to local disk or R2 by hash | Temporal, event bus, document versions UI | The `JobQueue` port |
| 007 Trust baseline | A receipts table written by `enforce()`; the eval set run in CI against a fixed corpus; a per-tenant cost circuit breaker | Dashboards, DuckDB analytics | Receipt schema v1 |

## 6. Constraints that apply to every sprint
- **Phase 1 is independent.** Keep-awake, the walkthrough video and the open-source MCP server never wait for these sprints.
- **The live preview keeps running.** Each sprint states any step needed on the hosted side (env vars, migrations against Neon). Migrations are additive first: add columns as nullable, backfill, then add constraints.
- **Free tiers only:** Render, Neon, Upstash, Cloudflare R2, and a Grafana Cloud or Langfuse free tier. A paid dependency is a stop condition.

## 7. Flexible decisions (can change freely)
- Which LLM, embedding model, host or UI library to use.
- Redis versus Postgres for cache and limits.
- Whether the gateway runs in-process or as its own service.
- Which queue library or workflow engine to use (Postgres first, Temporal later).
- Which analytics store to use.

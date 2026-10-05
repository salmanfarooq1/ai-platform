# Build history

The numbered build-history sections of the old README, moved here unchanged. They record how the platform was built (labs, then sprints). The product documentation is in `README.md` and `docs/`.

## Original introduction

Production grade AI backend platform built around memory-efficient ingestion, async HTTP, and eventually hybrid RAG retrieval with LangGraph agents.

Core idea: most AI pipelines fail at scale not because of the model, but because of poor infrastructure - loading files eagerly into memory, firing unbounded concurrent requests, or writing everything to disk at once. This project builds the infrastructure layer that handles all of that correctly.

Built incrementally over 12 phases, roughly one per week. Each lab isolates one concept, breaks it, measures it, fixes it, then integrates it into the platform. Code in `core/` is production-ready - scripts in `scripts/` show how it was built and tested.

---

## Key Results

| Lab | What is Proved | Result |
|-----|---------------|--------|
| 1.1 | `range` vs `list` memory | 381 MB → 0.0001 MB |
| 1.3 | Chunk iterator memory | 13,000× reduction |
| 1.4 | Generator pipeline memory | 4,800× reduction |
| 2.3 | Semaphore vs unbounded | 100% vs 57% success |
| 2.5 | Async pipeline memory | Constant at any file size |
| 3.3 | COPY vs row-by-row INSERT | 226× faster (102K rows/s) |
| 3.4 | Connection pooling | 1.6× faster, zero overhead |
| 4.1 | GIL limits CPU-bound threading | Threads ≈ Sequential, Processes ≈ 4x faster |
| 4.2 | Serialization break-even point | Sequential wins <1MB, Processes win >10MB (2.44x at 10MB) |
| 4.3 | Event loop responsiveness | Naive: 545ms avg delay → Hybrid: 2.58ms avg delay (2.53x pipeline speedup) |
| 6.2 | Semantic vs string cache hit rate | 41% → 74% on 100-query test set |
| 6.5 | End-to-end cost reduction via cache | ~60% cost reduction |
| 7.3 | Vector vs BM25 vs Hybrid precision | 0.17 / 0.16 / 0.17 Precision@5 (corpus ceiling is 0.20) |
| 7.5 | Reranker Contextual Precision & OOD Refusal | +35.5% Precision lift (0.450 → 0.610), 0.800 Recall, 100% OOD Refusal |
| 9.1 | Multi-stage Docker build | 2.5GB → 600MB (with reranker) / 119MB (public-preview, no torch) |
| 9.2 | Token budget enforcement | 500K tokens/day/tenant, auto-reset at midnight UTC |

---

## 1. Memory-Efficient Ingestion

### Lab 1.1: Memory Experiments
Proved lazy evaluation (`range`) saves massive memory vs eager loading (`list`). This prevents OOM errors in pipelines.

### Lab 1.2: Memory Leaks
Learned how circular references bypass Python's reference counting and how garbage collection fixes leaks.

### Lab 1.3: File Chunk Iterator
Built production iterator/context manager to process huge files with O(1) memory usage.

### Lab 1.4: Generator Pipeline
Built generator pipeline for massive datasets with constant memory usage.

### Lab 1.5: Integration Test
Integrated all ingestion modules above and tested end-to-end.

---

## 2. Async HTTP & Concurrency

### Lab 2.1: Event Loop Deep Dive
Explored asyncio event loop, proved it's single-threaded, understood how it handles concurrency without threads.

### Lab 2.2: Concurrency Trap
Found what happens when you fire too many concurrent requests. Key finding: over-concurrency kills performance.

### Lab 2.3: Controlled Concurrency
In Lab 2.2, 1000 unbounded requests = 57% success rate. With `Semaphore(500)` = 100% success at same throughput (95 req/s vs 90 req/s). Controlled concurrency wins.

### Lab 2.4: Production HTTP Client
Built `AsyncHttpClient` - handles thousands of API calls with automatic retries, semaphore rate limiting, and error handling.

### Lab 2.5: Integration Pipeline
Combined ingestion and HTTP layers into a full async pipeline: read → clean → batch → embed → store. Generator chain keeps memory constant regardless of file size. Concurrency drives throughput, memory scales with concurrency not file size.

---

## 3. PostgreSQL + pgvector

### Lab 3.1: Database Setup
Set up PostgreSQL + pgvector via Docker. Connected with psycopg2 (sync) first, then asyncpg (async). Registered pgvector extension and created vector(768) schema.

### Lab 3.2: Row-by-Row vs Bulk Insert
Benchmarked three psycopg2 approaches. `executemany` is a lie (1.03x). `execute_batch` gives 2.27x. Both still too slow for production.

### Lab 3.3: asyncpg COPY
asyncpg's `copy_records_to_table()` hit 102,106 rows/s, a 226x speedup over row-by-row. COPY bypasses SQL parsing entirely.

### Lab 3.4: Connection Pooling + Integration
Built `asyncpg.create_pool()` with `init=register_vector`. Pool concurrent (0.63s) beats fresh-connect-per-batch (0.99s). Integrated everything into `db_ingest.py`: read → clean → embed → COPY to postgres. 1,297 chunks/sec, all rows verified in DB.

---
## 4. GIL, Multiprocessing & Hybrid Concurrency

### Lab 4.1: GIL Proof

Proved the GIL prevents parallel execution for CPU-bound threads. Four threads running sum(i*i for i in range(5M)) takes the same time as sequential. Four processes take ~4x less. The fix for CPU-bound work is ProcessPoolExecutor, not ThreadPoolExecutor.

### Lab 4.2: Serialization Overhead

Every process boundary has a pickle cost. Found the break-even: sequential wins below ~1MB-10MB of data per task, processes win above ~10MB. Small tasks (DB writes, tiny cleanups) should never use multiprocessing, the overhead dominates. Large tasks (embedding batches, chunking large docs) benefit from it.

### Lab 4.3: Hybrid Async + Multiprocessing

Proved that CPU work called directly inside an async coroutine blocks the entire event loop: average 545ms delay, nothing else can run. run_in_executor() offloads CPU work to a process pool while immediately returning control to the event loop. Result: 2.58ms average delay, 2.53x pipeline speedup. This is the production pattern for core/pipeline/.

## 5. RAG API & Structured Outputs

### Lab 5.1: The FastAPI LIFO Onion
Built the API layer with robust middlewares. Proved that FastAPI mounts middleware in Last-In-First-Out (LIFO) order, and fixed our `FinOpsMiddleware` by strictly ordering it after the Request ID generation.

### Lab 5.2: LiteLLM Abstraction
Replaced raw provider SDKs with LiteLLM. Moving between local Ollama and production GPT-4o is now a single config change without rewriting the core `acompletion` logic.

### Lab 5.3: Structured Pydantic Outputs
Forced the LLM into returning a strict `GeneratedAnswer` schema to eliminate regex parsing. Eradicated silent database corruption by catching hallucinations loudly at the Pydantic validation boundary.

### Lab 5.4: Math & Mislabeled Files
Updated the vector search to use Cosine Distance (`<=>`) for accurate similarity scoring (`1.0 - distance`), and bulletproofed the chunker routing against mislabeled or unknown file extensions.

---

## 6. Caching & Cost Optimization

### Lab 6.1: Cache-Aside with Redis
Built exact-match Redis caching: hash the query + namespace + top_k → check Redis first, only hit the DB and LLM on a miss. Cache hit returns in ~1ms vs ~800ms full pipeline.

### Lab 6.2: Semantic Caching
Exact match only catches identical queries. Added a Redis HNSW vector index: embed the query, find the nearest cached query by cosine similarity, return the cached answer if similarity > 0.95. Hit rate went from 41% to 74% on the test set. The key insight: you need the embedding for vector search anyway, so the semantic cache check costs nothing extra.

### Lab 6.3: Model Routing by Query Complexity
Not every query needs the most expensive model. A word count + keyword heuristic routes short factual queries to the cheap model and longer analytical queries to the full model. Measured cost per 100 mixed queries before and after. The classifier was removed later (Decision 7 in `docs/ARCHITECTURE.md`); routing now picks one model.

### Lab 6.4 & 6.5: Integration & Benchmark
Wired all three layers (exact cache → semantic cache → full pipeline) into the search route. Dual-layer cache reduces LLM calls by ~60% on a realistic query distribution. Benchmark committed to `benchmarks/lab_6.5_cache_benchmarks.json`.

---

## 7. Hybrid RAG & Evaluation

### Lab 7.1: Vector Search Failure Cases
Documented 5 concrete failure modes of pure vector search on the legal compliance corpus. Article numbers drift (searching "Article 5" returns "Article 6" content). Rare identifiers like section numbers compress into generic topics. Negation is invisible to cosine similarity. These aren't theoretical: all five were reproduced with actual queries against the real database.

### Lab 7.2: FTS Index Migration
Added a `tsvector` full-text search column to the documents table and a GIN index. Migrated the schema and verified BM25 scoring works via `ts_rank()`.

### Lab 7.3: Hybrid Retrieval (RRF)
Built the hybrid retriever: run BM25 and vector search in parallel, merge by Reciprocal Rank Fusion (k=60). Neither retriever dominates, documents scoring well in either list get a boost. Also discovered the AND/OR threshold problem: PostgreSQL's `plainto_tsquery` uses AND by default, which returns empty results for long natural language queries. Fixed with `BM25_OR_THRESHOLD = 5`: queries under 5 words use AND (precision mode), 5+ words rewrite to OR (recall mode).

Precision@5 results across 20 manually labeled queries (corpus ceiling is 0.20 = 1 relevant chunk per query in top 5):

| Mode | Precision@5 | Notes |
|---|---|---|
| Vector only | 0.17 | Fails on exact terms, article numbers |
| BM25 only | 0.16 | Fails on semantic paraphrases |
| Hybrid RRF | 0.17 | Captures both, 85% hit rate at the ceiling |

### Lab 7.5: Cross-Encoder Reranking + Robust DeepEval v5 Benchmark
Added a two-stage pipeline: hybrid RRF produces up to 20 candidates, cross-encoder (`ms-marco-MiniLM-L-6-v2`) re-scores them by reading query+chunk together and picks top 5.

Before enabling this in the async API, ran an event-loop safety check (Lab C.5): confirmed that when reranking is offloaded via `run_cpu_bound()`, the event loop heartbeat max gap is 11ms, well under the 20ms safe threshold. `rerank=True` is now the production default.

Evaluation was executed using `scripts/lab_7.5_deep_eval_v5.py` with `gemini-3.5-flash` for generation and `gemini-2.5-pro` for judging across dual-namespaces (`legal` GDPR/CCPA + `kyc_aml` 31 CFR 1010) and isolated OOD guardrail triplets:

| Metric (In-Domain) | Hybrid RRF (Base) | Hybrid RRF + Reranked | Delta |
|---|:---:|:---:|:---:|
| **Faithfulness** | **1.000** | 0.686 | -31.4% |
| **Answer Relevancy** | **0.755** | 0.700 | -5.5% |
| **Contextual Precision** | 0.450 | **0.610** | **+35.5%** |
| **Contextual Recall** | **0.800** | **0.800** | 0.0% |
| **OOD Refusal Pass Rate** | **100% (3/3)** | **100% (3/3)** | 0.0% |

- **Contextual Precision Lift:** Cross-Encoder reranking significantly improved ranking order (+35.5% lift from 0.450 to 0.610), ensuring top-ranked chunks contain the most relevant statutory provisions.
- **Contextual Recall:** Achieved 0.800 across real legal and financial compliance chunks (up from 0.40 in synthetic tests).
- **Isolated OOD Refusal:** 100% exact refusal match on non-compliant queries without corrupting in-domain RAG metrics or wasting judge API calls.
- **Visual Analytics:** High-resolution dashboard generated at `benchmarks/lab_7.5_eval_v5_comparison.png` via `scripts/plot_eval_v5.py`.

---

## 8. Governance, Data Ops, and Testing Foundations

### Lab 8.1: Document Lifecycle & Hashing
Built a document registry using a composite primary key `(document_id, namespace)`. Implemented SHA-256 payload hashing to prevent duplicate embedding costs and cleanly handle document updates by deleting old chunks before re-ingestion.

### Lab 8.2: API Rate Limiting
Implemented an LIFO `RateLimitMiddleware` using Redis fixed-window counters (`INCR` + `EXPIRE`). Protected the application layer from unbounded costs and abuse. Since Sprint 003 the counter is keyed on the authenticated principal, not on a caller-supplied namespace. Since Sprint 004 the limit is the `rate` stage of the gateway (`gateway/limits.py`), and the middleware class is gone.

### Lab 8.3: Input & Output Guardrails
Wired up regex-based input validation to block prompt injection (e.g., "ignore instructions") and applied strict query length boundaries. Added an output guardrail based on retrieval `rrf_score` to flag out-of-domain answers below the `CONFIDENCE_FLOOR`.

### Lab 8.4: Pytest 3-Tier Architecture
Established a production-grade testing foundation. Configured `pytest-asyncio` and `pytest-cov`, and used `pytest_collection_modifyitems` to dynamically auto-tag tests as `unit`, `integration`, or `e2e` based on their directory structure. All 39 unit tests pass with >90% coverage on core services.

---

## 9. Production Deployment, CI, Guardrails & Governance

### Containerization
Multi-stage `Dockerfile` (`python:3.11-slim-bookworm` builder + runtime). Builder installs Poetry and all dependencies; runtime copies only the virtualenv and app code. An `INCLUDE_RERANK` build arg controls whether `sentence-transformers`/torch ship in the image: false for the 512MB public-preview tier (119MB image, 240MB steady-state RSS), true for a prod build with reranking enabled. See Decision 20 in `docs/ARCHITECTURE.md`.

### Production Docker Compose
`docker-compose.prod.yml` runs API + PostgreSQL (pgvector) + Redis stack with health check dependencies (`pg_isready`, `redis-cli ping`) and automatic schema initialization via `docker-entrypoint-initdb.d/`.

### Free-Tier Cloud Deployment
`FEATURES["reranker_enabled"] = MODE != "public-preview"` disables the cross-encoder in public-preview mode to stay inside 512MB RAM while keeping hybrid RRF search. Public-preview mode's embedding model is `gemini/gemini-embedding-001` (truncated to 768 dims), not the local `nomic-embed-text` default, since no cloud free tier runs an Ollama sidecar. Deployed via a Render Blueprint (`render.yaml`); see `docs/render-deployment.md` for the full runbook and Decisions 21-23 in `docs/ARCHITECTURE.md` for why.

### Token Budget Enforcement
Built `TokenBudgetMiddleware` backed by a Redis counter (`budget:{tenant_id}:{date}`, per tenant since Sprint 003). Evaluated at the middleware boundary (0.1ms latency, $0.00 cost when budget is exceeded). Counter expires after 25 hours (automatic midnight UTC reset). Since Sprint 004 the check is the `budget` stage of the gateway, with the same Redis key and the same 429 code. `TokenBudgetMiddleware` is gone.

### Health Check Expansion
Expanded `/health` endpoint with active probes for database (`SELECT 1`), Redis ping, LiteLLM embedding model reachability, process `uptime_seconds`, and deployment `mode`.

---

## 10. LangGraph Agent

### Agent Architecture
A compliance research agent using LangGraph: one reasoning/retrieval role with two tools:
* `retrieve_chunks`: the existing hybrid retriever, `mode` as a parameter rather than a tool per strategy
* `list_namespaces`: lets the agent discover available document scopes instead of relying on a hardcoded list

Plus a deterministic synthesis step and an optional verifier role that checks the drafted answer against retrieved chunks, toggleable per request and via a deployment-wide flag.

Every agent answer includes citations, a confidence score, the model used, verification status, and full query cost (every reasoning and verification turn, not just the last step).

### Key Results
| Metric | Value |
|---|---|
| Single-step queries | 1 retrieval + synthesis, ~3-4s |
| Multi-step queries | 2-4 retrievals + synthesis, ~8-12s |
| With verifier enabled | +1 LLM call minimum; +1 full retrieval round if a retry is triggered |
| Agent endpoint | `POST /v1/agent/query` |

---

## 11. MCP Server & Cost Tracking

### MCP Integration
The platform now speaks the Model Context Protocol (MCP), allowing external AI clients (Claude Desktop, Cursor, VS Code) to discover and invoke our RAG tools programmatically over SSE transport.

| Component | Count | Details |
|---|---|---|
| Tools | 5 | `list_namespaces`, `search_documents`, `multi_namespace_search`, `get_ingestion_status`, `get_cost_summary`. Bearer credential required; search needs `query`, the others `kb:read`; all run as the caller's tenant |
| Resources | 3 | The caller's knowledge bases, feature flags, document chunks (the tenant's own; `kb:read`) |
| Prompts | 2 | Compliance research workflow, cost audit workflow |

### Persistent Cost Tracking
A `usage_log` table in Postgres stores one row per LLM-consuming request. The FinOps middleware writes via `asyncio.create_task` (fire-and-forget). Token booking after the work stays best effort; decision records do not (section 15). Monthly cost reports are a simple `GROUP BY` query.

### Gap Fixes
- Input guardrail added to `/agent/query`
- `list_namespaces` made async for event loop safety
- Verifier model built once as closure in graph constructor

---

## 12. Production Hardening

### What Changed
- Fixed invalid Postgres expression index on `usage_log`
- Added `rerank_score` to scoring waterfall for score-order consistency
- Injected namespace into `/search` usage tracking
- Hardened MCP resource error handling
- Added rate limiting for `/mcp/sse` endpoint
- Extracted magic numbers into named constants
- Expanded test suite with FinOps, search schema, and shared fixtures

### Final Architecture
| Layer | Components |
|---|---|
| Transport | FastAPI + SSE (MCP) |
| Middleware (outermost first) | CORS → Request ID and trace ID → Logging and error body → Latency → Auth (Sprint 003) → FinOps. The rate limit and token budget were middleware here; since Sprint 004 they are gateway stages |
| Routes | `/v1/search`, `/v1/ingest`, `/v1/agent/query`, `/v1/documents`, `/v1/analytics/summary`, `/v1/feedback`, `/v1/quality-report`, `/v1/config`, `/v1/health`, `/v1/mcp/sse`. `/` and `/health` stay unversioned. |
| Errors | One format everywhere: `{"error": {"code", "message", "request_id"}}` |
| Observability | JSON logs with `request_id` and `trace_id`; OpenTelemetry spans; `X-Request-ID` and `X-Trace-ID` on every response |
| Services | Hybrid retriever, semantic cache, guardrails, usage writer |
| Agent | LangGraph (reasoning → tools → synthesis → verification) |
| Storage | Postgres (pgvector) + Redis |

---

## 13. Platform Base (Sprint 002)

- **Config:** `core/settings.py` validates the environment once. `MODE=public-preview` or `prod` without `DATABASE_URL` and `REDIS_URL` stops the process at startup. `config.py` keeps its public names.
- **Migrations:** Alembic, forward-only. `poetry run alembic upgrade head` creates the schema (later sprints added `0002`–`0008`; `0008` is the job queue, the outbox and consumer dedupe). The baseline `0001` is idempotent, so it is safe on a database that already has the tables. The Docker image runs it before starting uvicorn.
- **API:** every product route is under `/v1`. Old unversioned paths return 404 in the standard error format. MCP clients connect to `/v1/mcp/sse` (see `claude_desktop_config.json`).
- **Observability:** logs are one JSON object per line. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to export traces. Without it, no exporter and no background thread is created.
- **Tests:** `unit` has no external services. `integration` and `e2e` use a real Postgres and Redis, with fake LLM and embeddings, and skip with a reason when the services are down. A network guard fails any test that tries to reach a provider.

---

## 14. Identity and Tenancy (Sprint 003)

- **Who is calling:** every `/v1` route except `/v1/health` needs `Authorization: Bearer <token>`. A token is an API key (`gap_<prefix>_<secret>`, only a SHA-256 hash is stored) or a JWT (`JWT_JWKS_URL` or `JWT_SECRET`, with `JWT_ISSUER` and `JWT_AUDIENCE`). The tenant comes only from the verified credential, never from a header, query string or body. A missing or bad credential is 401, a missing scope is 403.
- **Scopes:** `kb:read`, `kb:write`, `query`, `agent`, `admin` (admin satisfies all). Search and feedback need `query`, ingest needs `kb:write`, documents, config and analytics need `kb:read`, the agent needs `agent`. MCP needs `query`.
- **Isolation:** migrations `0002`–`0004` add `tenants`, `principals`, `api_keys` and `knowledge_bases`. `documents`, `document_registry`, `usage_log` and `feedback` carry `tenant_id`. Postgres row-level security (`tenant_id = current_setting('app.tenant_id')`) is on every tenant-owned table, and a request-path query only runs inside `tenant_connection()`, which sets that setting for the transaction. No setting means zero rows.
- **Two database roles:** the app connects as `gap_app` (`DATABASE_URL`), a role without superuser or `BYPASSRLS`, because those bypass row-level security. The app refuses to start otherwise. Migrations and the admin CLI use the owner role (`MIGRATION_DATABASE_URL`).
- **Knowledge bases:** the old `namespace` parameter is now a knowledge-base slug checked against the caller's own knowledge bases. An unknown KB and another tenant's KB both give the same 404 `kb_not_found`.
- **Caches and limits:** cache keys and the semantic-cache index carry the tenant. The rate limit counts per principal, the daily token budget per tenant.
- **Hosted preview:** the UI's nginx proxy only forwards `/v1` to the API and adds no key. A visitor gets a read-only session for the principal in `PREVIEW_PRINCIPAL_ID` (ADR-0007). The ordered steps for the hosted database are in `docs/render-deployment.md`.

---

## 15. Gateway core (Sprint 004)

- **One entry point:** `gateway.enforce(ctx, action)` returns a `Decision`, and `require()` raises `GatewayDenied` instead. Every model, tool and knowledge-base call goes through it: the search, ingest, documents and agent routes, every agent LLM and tool call, and the MCP tools and resources. Actions are `kb.read`, `kb.write`, `model.invoke`, `tool.call`, `agent.run`, `feedback.write` and `analytics.read`.
- **Stages, in order:** principal, boundary, policy, input guardrails, rate limit, token budget (`gateway/stages.py`). The first deny wins. The stage list is data, so a new stage is one function and one entry. The rate limit and budget keep their Redis keys, limits and 429 codes; they used to be middleware.
- **Boundary:** the `ExecutionBoundary` is frozen, built once per request from the caller's scopes and the tenant's active policy, and it can only narrow. The agent and its tools get the boundary, never the raw principal.
- **Policies:** a tenant narrows what it may do with a policy document: knowledge bases, tools, models, tool-call and token limits. Versions are append-only, one is active per tenant, and the app role can only read them. Publish with `scripts/admin/identity.py set-policy <tenant> <file.json>` and read with `show-policy`. With no policy, scopes grant against the platform defaults, which is the same access as before Sprint 004.
- **Decision records:** every call writes one `gateway_decisions` row, allow or deny: tenant, principal, action, resource, outcome, stage, reason, policy version, and the SHA-256 of the input. The text is never stored. Row-level security is forced on the table, and `gap_app` can only SELECT and INSERT.
- **Fail closed:** any exception in a stage is a deny (`internal_error`). If Redis is down, the rate and budget stages deny with 503 `dependency_unavailable`. If the decision write fails on an allow, the call is denied with 503 `decision_unrecorded` and the work is not done. Booking tokens after the work stays best effort, because the tokens are already spent.
- **HTTP mapping:** a policy, boundary or internal deny is 403 `policy_denied` (the reason is in the message), a blocked query is 400 `query_blocked`, limits are 429, and dependency or record failures are 503. An agent run that hits a denial ends with a partial answer marked `flagged`.
- **Guards:** an import-lint test keeps `litellm`, `langchain_litellm` and `asyncpg` out of the agent tools and the MCP code, and keeps every provider SDK inside `adapters/` (Sprint 006, ADR-0005), and an AST check proves every agent tool, MCP tool and MCP resource calls the gate. See Decision 26 in `docs/ARCHITECTURE.md` and `docs/adr/0006-gateway-enforce-pipeline.md`.

---

## 16. Trust baseline (Sprint 008)

- **Receipts:** every decision row joins a per-tenant hash chain. `GET /v1/receipts/{decision_id}` returns the decision, its chain link and an Ed25519 signature (`audit:read`). `GET /v1/receipts/keys` lists the public keys. Check one offline, with nothing from this code base: `python scripts/verify/receipt.py receipt receipt.json --keys keys.json`. Check a whole chain with `python scripts/verify/receipt.py chain --dsn <owner url> --tenant <id>`. Set `RECEIPT_SIGNING_KEY` (base64 of 32 bytes) in `public-preview` and `prod`; local mode makes a throwaway key (ADR-0012).
- **Retention:** decision records are kept `DECISION_RETENTION_DAYS` (90). A tenant can have its own: `scripts/admin/identity.py set-retention <tenant> <days|default>`. A worker queues a purge job each day and the chain keeps a checkpoint. The Trust page shows the settings read only.
- **Eval gate:** `poetry run python scripts/eval/run_gate.py` runs a fixed suite with the fake LLM and fails when a score drops below `scripts/eval/baseline.json` minus its tolerance. CI runs it. `REAL_EVAL=1 python scripts/eval/run_real.py` is the manual run with real providers; it spends money.
- **Cost cap:** a `cost` stage denies with 429 `cost_cap_exceeded` once a tenant spends `DAILY_COST_CAP_USD` in a UTC day. A tenant policy may set `daily_cost_cap_usd` lower. With Redis down the call is denied.
- **Metrics:** `/metrics` (Prometheus text): `http_requests_total`, `http_request_duration_seconds`, `gateway_decisions_total`, `jobs_total`, `outbox_lag_seconds`. Open in local mode; elsewhere it needs an `admin` key unless `METRICS_PUBLIC=true`. `docker compose --profile observability up -d` adds Prometheus and a provisioned Grafana dashboard ("Platform trust", http://localhost:3000). `scripts/verify/observability.sh` checks them end to end.
- **Trust page:** `/app/trust` verifies a receipt by decision id (or a pasted receipt), shows retention and the eval gate history, and links to Grafana when `GRAFANA_URL` is set.

## 17. Sandboxed agent runs (Sprint 009)

- **What it is:** with `AGENT_RUNTIME=openshell`, a worker runs each agent run inside an [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) sandbox (Apache-2.0, pinned 0.1.2). The sandbox's only network route is this platform's gateway, so it cannot call a model provider. It can write only one work directory, and it has CPU, memory and wall-clock limits. The default, `queued`, is unchanged and needs none of this.
- **How the agent calls out:** the program in the sandbox (`sandbox_agent/`) has no model key and no database. It calls `/v1/sandbox/runs/{execution_id}/tools/{name}` and `/model` with a run token that is valid for that run only (hash stored, short-lived, revoked when the run ends). Every call goes through `enforce()` and is recorded with the run's `execution_id`.
- **Tool arguments:** a policy may hold `tool_arguments`, a JSON Schema per tool. A call whose arguments do not fit is denied with `tool_argument_not_allowed`. Example policy fragment: `{"tool_arguments": {"retrieve_chunks": {"type": "object", "properties": {"top_k": {"type": "integer", "maximum": 3}}, "required": ["query"]}}}`.
- **Events:** the sandbox's start, exit, refused connections and limits go to `sandbox_events`. `GET /v1/agent/runs/{execution_id}` returns them with the run's decisions merged by time, and the Agent runs page shows them on the step timeline.
- **Run it and check it:** `docs/runbooks/openshell.md` (install, images, kernel requirements, troubleshooting) and `OPENSHELL_SANDBOX_IMAGE=<image> scripts/verify/openshell.sh`. The SDK is installed only for that script, by hash (`scripts/verify/openshell-requirements.txt`); it is not a dependency of the platform. The tests run against a fake sandbox (`tests/fake_sandbox.py`), which is not a recording of a real run.
- **Verified:** A2 to A5 and the memory and CPU limits ran live against OpenShell 0.1.2 with the Docker driver in the build container (`planning/sprints/009-sandboxed-agents/evidence/openshell-live.txt`). **Not verified:** the standard `ghcr.io` images (the container could not pull them), Podman, Kubernetes, WSL 2, other versions, a real model.

## 18. Kafka event bus (Sprint 010)
- **What it is:** `EVENT_BUS=kafka` makes the outbox relay publish the platform's events to Kafka (`aiokafka`, Apache-2.0, pinned 0.14.0). The Postgres outbox stays the default and is still written in the decision's transaction, so Kafka is never reached inside a request and a decision is never lost because of the bus.
- **Topics:** `platform.<type without version>`, for example `platform.gateway.decision`. The key is the tenant id, so one tenant's events keep their order. Events are CloudEvents in binary mode (`ce_*` headers).
- **Consumers:** a consumer group handler is deduped by CloudEvent id (`processed_events`). The offset is committed after the handler succeeds. After `KAFKA_MAX_ATTEMPTS` failures the message goes to `<topic>.dlq` with an error header. No consumer ships with the platform yet.
- **Run it:** `docker compose --profile kafka up -d redpanda`, `docker compose --profile kafka up kafka-topics`, then `EVENT_BUS=kafka KAFKA_BOOTSTRAP=localhost:19092 poetry run python -m workers`. See `docs/runbooks/kafka.md`. Switching back to `EVENT_BUS=outbox` needs no migration.
- **Check it live:** `scripts/verify/kafka.sh` runs the contract suite, the ordering test and the restart test on a real Redpanda. The pytest suite runs the same tests on an in-memory broker (`tests/fake_kafka.py`, a model of the broker, not a recording).

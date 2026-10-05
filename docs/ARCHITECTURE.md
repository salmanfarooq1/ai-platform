# Architecture Decisions

## Decision 1: run_in_executor for CPU-bound work
**Context:** Fast API is single-threaded, running CPU bound tasks directly would block the event loop.
**Decision:** `run_in_executor()` runs CPU-bound tasks in a saperate process, event loop stays free.
**Trade-off:** cost, pickle and unpickle overhead, only tasks taking more than ~10ms are worth it. 

## Decision 2: Domain-Specific Chunking Strategy
**Context:** Single chunking strategy is inefficient for all document types. An OpenAPI spec needs different chunking than a regular pdf document. 
**Decision:** `CHUNKER_REGISTRY` dispatches by file extension. 
- .txt/.md: `recursive`/`header-aware split`.
- .json : `chunk_openapi_spec` (one operation per chunk)
**Trade-off:** Document type has to be detected at ingestion time, a mislabled file with wrong extension would fall back to default chunker.

## Decision 3: LiteLLM over Langchain/custom LLM router
**Context:** Each LLM provider has it's own auth, response format etc. yet LLM calls must be standardized. The goal is replace code changes with config changes. 
**Decision:** LiteLLM, provides `acompletion()` function, standard way to call any LLM. Any future model change would require a simple config change.
**Trade-off:** LiteLLM is still a dependency that might break, mitigated by pinning the version.
 - Why not Langchain: Langchain is an orchestration layer.LiteLLM is just a model access layer. Langchain has its provider routing coupled with own objects such as `BaseMessage`, `Runnables`, which add abstraction and complexity, while limiting our flexibility.   

## Decision 4: Structured Outputs over regex parsing
**Context:** LLM outputs need to be parsed, but they are prone to hallucinations and inconsistent formatting. Regex is brittle in these scenerios.
**Decision:** Structured outputs by using `GeneratedAnswer = response_format()`. LLM output is constrained at decoding level and validated by Pydantic.
**Trade-off:** Not every llm supports structured outputs, the fallback is Json mode with validation. There is still a risk of well-structured hallucination, it may provide a fabricated chunk_id.

## Decision 5: Inline citations, RAGAS vs user trust
**Context:** RAGAS already measures faithfulness, yet it is developer-facing. We need a user-facing trust system, most of regulated industries need this for audit trails and compliance.
**Decision:** Inline citations, this provides answers traced back to actual sources through chunk_id. 
**Trade-off:** Citations add 20% more tokens, including chunk_ids and instructions. Another option is post-hoc citation matching with embedding similarity, this saves tokens but adds extra layer with moving parts, adding a dependency on similarity search. Inline citations also are prone to hallucination, LLM can provide a chunk_id that does not actually back up the source, and RAGAS cannot verify this because it looks in different direction.

## Decision 6: Semantic cache over exact-match cache
**Context:** After wiring up basic Redis caching, the hit rate was around 40%. The reason: queries like "what is AI?" and "explain artificial intelligence" are treated as completely different keys. They miss the cache every time even though they'd get identical answers.
**Decision:** Added a vector index in Redis (HNSW) so that before doing a full DB + LLM round trip, we check if any previously cached query is semantically close enough (cosine similarity > 0.65) to serve the same answer. Hit rate went from 41% to 74% on the same query set.
**Trade-off:** You need to embed the query before checking the cache, which costs ~10ms. But you were going to embed it for vector search anyway, so you compute it once and use it for both. The 0.65 threshold took tuning. At 0.55 precision dropped (wrong answers served), at 0.95 it collapsed back to near-exact string matching with <5% improvement over exact cache. 0.65 was the empirical sweet spot measured in Lab 6.2.

## Decision 7: Heuristic model routing by query complexity
**Context:** Running every query through the most expensive model is wasteful. A question like "what is the return policy?" and "compare GDPR and CCPA fine structures across jurisdictions" are not the same problem. They shouldn't cost the same.
**Decision:** A simple word count + keyword heuristic classifies queries as simple or complex before the LLM call. Simple queries go to the cheaper/local model. Complex ones go to the configured production model.
**Trade-off:** The heuristic is obviously imperfect: a short question can be conceptually hard, a long one can be trivial. The risk is misclassification giving a poor answer on a simple-looking but complex question. Acceptable for now because the quality gap between models is smaller than it looks for this corpus. Something like a small classifier or LLM-based routing would be the real fix, deferred.
Superseded: the complexity classifier was removed in commit `efde99f`. Routing now picks one model and `generate_with_routing()` calls `generate_with_citations()`.

## Decision 8: TTL-based cache invalidation over full CDC
**Context:** Once an answer is cached, what happens when the source document changes? A user could get a cached response about a compliance policy that was updated last week and we'd never know.
**Decision:** Cache TTL is set to 3600 seconds (1 hour). Documents in this system change quarterly at most, so 1 hour staleness is an acceptable window. When a document is replaced, the document_id changes, which means old chunks are deleted and the new ones will naturally miss cache and repopulate it.
**Trade-off:** This is not full CDC. Proper invalidation would tag every cache entry with its source document_id and delete on document update. That's architecturally correct but complex to implement. TTL is the interim mitigation: simple, proven, and fine for low-change-frequency documents. Full CDC invalidation stayed deferred (see Known Open Gaps below).

## Decision 9: Hybrid RRF over pure vector or pure BM25
**Context:** After running Lab 7.1, I documented 5 concrete failure modes of pure vector search on the legal corpus. Article numbers like "Article 5" drift to "Article 6" because they sit in the same semantic neighborhood. Section identifiers like "1798.155" return garbage because embeddings compress rare tokens into generic topics. Negation ("does NOT apply") is essentially invisible to cosine similarity.
**Decision:** Hybrid RRF (Reciprocal Rank Fusion with k=60) merges vector results and BM25 results by rank position, not by score. Neither retriever dominates: a document scoring well in either list gets a lift. This fixes the failure modes above without throwing away semantic search's strength on paraphrase queries.
**Trade-off:** RRF doesn't use the raw scores from either retriever. It only uses rank position. So a BM25 result with score 0.9 and one with score 0.4 look identical to RRF as long as they're at the same rank. This is intentional (it prevents one retriever's score scale from overwhelming the other) but it means you lose score magnitude information. k=60 was benchmarked against k=20 and k=100. It's the literature default and gave the best empirical precision on this corpus.

## Decision 10: Dynamic AND/OR operator in BM25 based on query length
**Context:** PostgreSQL's `plainto_tsquery` connects all tokens with AND by default. For short keyword queries like "GDPR Article 5", this is exactly what you want: strict intersection, maximum precision. But for a 7-word natural language question, the probability of all tokens appearing in a single chunk drops close to zero. BM25 was returning empty results on every conversational query.
**Decision:** `BM25_OR_THRESHOLD = 5`. Queries under 5 words use the strict AND operator (precision mode). Queries with 5+ words dynamically rewrite the tsquery from AND to OR (recall mode). This is a one-line change in SQL but it fundamentally changes the retriever's behavior based on query intent.
**Trade-off:** The threshold of 5 is a heuristic. A 4-word query could be conversational, a 6-word query could be a precise identifier lookup. The failure mode in either direction is manageable though: false ANDs produce empty results (obvious failure), false ORs produce extra candidates which the cross-encoder then re-ranks down. Reranking partially saves us from over-broad BM25.

## Decision 11: Cross-encoder reranking enabled in production, disabled in public-preview
**Context:** After hybrid RRF, answer relevancy was 0.7983 for the RRF-only mode. Adding the cross-encoder reranker jumped it to 0.9167, a meaningful +0.12 improvement. The model is `cross-encoder/ms-marco-MiniLM-L-6-v2`, runs locally with no API cost. But it takes ~380ms for inference, which blocks the event loop if called directly inside an async handler.
**Decision:** Reranking runs via `run_cpu_bound()`, offloaded to a `ProcessPoolExecutor`. Lab 7.5 confirmed that in offloaded mode, the event loop heartbeat max gap is 11ms, well under the 20ms safe threshold. So `rerank=True` is the default in production. In the public-preview deployment (512MB RAM free tier), reranking is disabled: the model alone is ~200MB and would OOM the container. Public-preview mode uses RRF-only, which still significantly outperforms pure vector.
**Trade-off:** The cross-encoder scores are raw logits, unbounded, not in [0,1]. We deliberately don't expose `rerank_score` as the confidence value in the API response because showing an unbounded logit as a percentage would be misleading. Only `rrf_score` is surfaced as the relevance signal. Reranking changes ordering silently, which is correct behavior.
Superseded by the Sprint 000 mode rename (`planning/DECISIONS.md`): the hosted mode is named `public-preview`.

## Decision 12: Rate Limiting Middleware
**Context:** We needed a way to prevent API abuse and control costs per tenant namespace. Relying solely on the database or downstream LLM provider for rate limits exposes the app layer to unbounded resource consumption.
**Decision:** We implemented a LIFO `RateLimitMiddleware` using a fixed-window counter in Redis (`INCR` + `EXPIRE`). Limits are enforced per `namespace` (changed in Sprint 003: the limit is now per authenticated principal, see Decision 25).
**Trade-off:** Fixed-window limits are susceptible to burst traffic at the edge of the window. A sliding window would be more accurate but adds complexity and performance overhead. For our scale, fixed-window is a pragmatic choice.
Superseded by Decision 26 (Sprint 004): the rate limit is the `rate` stage in `gateway/stages.py`, and `api/middleware/rate_limit.py` is deleted.

## Decision 13: Document Lifecycle & Content Hashing
**Context:** Re-ingesting the same document repeatedly wastes vector storage and embedding tokens. We needed a mechanism to detect duplicate content and handle document replacement cleanly without leaving orphaned chunks.
**Decision:** We use SHA-256 content hashing to fingerprint documents upon ingestion. The hash and status are tracked in a `document_registry` table using a composite primary key `(document_id, namespace)` (since Sprint 003: `(tenant_id, namespace, document_id)`). When a document is updated, its prior chunks are explicitly deleted before re-embedding.
**Trade-off:** Computing SHA-256 requires reading the file payload, which adds slight latency to ingestion. However, it completely eliminates duplicate processing costs, which far outweigh the hashing overhead.

## Decision 14: Multi-stage Docker build
**Context:** The application has heavy dependencies (sentence-transformers, numpy, PyTorch). A naive Dockerfile produces a 2-3GB image. Cloud deployment platforms have limited disk space on free tiers, and image pull time directly impacts cold start latency.
**Decision:** Two-stage build. Builder stage installs Poetry and resolves all dependencies. Runtime stage copies only the virtualenv and application code. Result: ~600MB image (still large due to PyTorch, but 60% smaller than single-stage).
**Trade-off:** Multi-stage builds are more complex to debug (you cannot `docker exec` into the builder stage). If a dependency fails to build, you need to add a `RUN` step in the builder stage to diagnose it. Worth it for the image size reduction.

## Decision 15: Daily token budget via Redis INCRBY
**Context:** FinOps middleware tracks cost per request but does not enforce a cap. A runaway script or misconfigured agent can exhaust the Groq API quota before anyone notices.
**Decision:** A Redis counter keyed by `budget:{namespace}:{date}` tracks cumulative tokens per namespace per day (since Sprint 003: `budget:{tenant_id}:{date}`, per tenant). The middleware checks the counter before processing and rejects with 429 when the budget is exceeded. The key expires after 25 hours (self-cleaning, no cron).
**Trade-off:** The budget check adds one Redis GET to every /search request (~0.1ms). The counter is eventually consistent: two concurrent requests could both pass the check and both consume tokens, briefly exceeding the cap by up to one request's worth. Acceptable for a compliance platform with moderate query volume.
Superseded by Decision 26 (Sprint 004): the budget check is the `budget` stage in `gateway/stages.py`, and `api/middleware/token_budget.py` is deleted.

## Decision 16: LangGraph agent: reasoning/retrieval role, deterministic synthesis, optional verifier role
**Context:** Some compliance questions require multi-step reasoning. "Compare GDPR and CCPA breach notification timelines" needs two separate retrievals and a synthesis step, the single-shot `/search` pipeline cannot do this in one call. Confidently-wrong answers are also a specific risk for a compliance product.
**Decision:** A single LangGraph graph with two LLM-invoked tools (`retrieve_chunks`, parameterized by `mode` rather than split per strategy; `list_namespaces` for discovery), a deterministic synthesis node that always runs via the same `generate_with_routing()` `/search` uses, and an optional verifier node that checks the drafted answer against retrieved chunks before returning it. The verifier is a second LLM role, not a second framework or agent-team, toggleable per request (`enable_verifier`) and with a deployment-wide kill-switch (`FEATURES["verifier_enabled"]`). Exposed at `/agent/query`.
**Why one reasoning role, not several:** A namespace-per-agent or strategy-per-tool split would be additional LLM calls doing what one parameterized call already does, with no new capability. The verifier is different: checking an answer against its sources is a distinct skill from producing the answer.
**Trade-off:** Agent queries are 2-5x slower than direct `/search` even without verification; with verification enabled (default) and a retry triggered, that multiplies further. Acceptable for complex research questions; simple factual queries should still use `/search`, and verification can be turned off per request when latency matters more. All LLM calls in the graph flow into `request.state.usage` alongside synthesis cost, so FinOps sees a query's full cost.


## Decision 17: MCP server over SSE transport, mounted into existing FastAPI app
**Context:** The platform exposes capabilities through REST routes (`/v1/search`, `/v1/agent/query`), but MCP-compatible AI tools (Claude Desktop, Cursor, VS Code Copilot) expect a Model Context Protocol server to discover and invoke tools programmatically. Building a separate MCP microservice would duplicate the retrieval stack.
**Decision:** Mount an MCP server (using the `mcp` Python SDK's `MCPServer` class) into the existing FastAPI app. SSE transport serves two endpoints: `GET /v1/mcp/sse` for the event stream and `POST /v1/mcp/messages/` for JSON-RPC requests. The SSE endpoint is a raw ASGI route, not a FastAPI endpoint function, because the transport writes the response itself. Tools delegate to the same `retrieve()`, `embed_query()`, and `check_input()` functions the REST routes use. The DB pool is injected via a context dict at startup, not through a global. Business logic is split into separate `tools.py`, `resources.py`, and `prompts.py` modules; `server.py` only holds the server instance.
**Why SSE, not stdio:** stdio requires the MCP server to run as a subprocess of the client. Our server already runs as an HTTP service. SSE lets any remote MCP client connect to the same deployed instance.
**Trade-off:** SSE connections are long-lived. Each connected MCP client holds one open HTTP connection for the session duration. On a free-tier instance with limited concurrent connections, practical concurrency is limited. Acceptable for development and single-user public-preview deployments. For multi-user production, Streamable HTTP transport would replace SSE.

## Decision 18: Persistent cost tracking in Postgres via fire-and-forget writes
**Context:** FinOps middleware computed per-request cost but only stamped it in response headers and logged it to stdout. Token budget middleware tracked daily totals in Redis but keys expired after 25 hours. Neither provided historical cost data for monthly reporting.
**Decision:** A `usage_log` table in Postgres stores one row per LLM-consuming request. FinOps middleware writes to it via `asyncio.create_task` (fire-and-forget) so a Postgres failure cannot slow down or crash a user-facing response. The MCP `get_cost_summary` tool queries this table for per-day breakdowns. Monthly aggregation is a standard SQL GROUP BY. The `MODEL_PRICING` dictionary is centralized in `config.py` so it is not buried inside middleware.
**Why fire-and-forget, not synchronous INSERT:** A synchronous write would add latency to every response and, worse, would crash the response if Postgres is temporarily unreachable. Cost tracking is important but not as important as serving the response.
**Trade-off:** If the app crashes between creating the task and executing the INSERT, that one row is lost. At the scale this platform operates, a missed row is negligible for monthly reports.

## Decision 19: Production hardening and final quality pass
**Context:** After 11 weeks of feature development, the codebase had accumulated several minor inconsistencies: a missing namespace in usage tracking, an invalid Postgres expression index, unguarded resource endpoints, and gaps in test coverage. None of these were blockers individually, but collectively they represented technical debt that would compound over time.
**Decision:** Dedicate an entire sprint to zero-feature hardening. Every known issue from code reviews, observation logs, and codebase audits was systematically resolved. Test coverage was expanded. Documentation was finalized. The goal was not to add capabilities, but to ensure every existing capability was production-grade.
**Trade-off:** No new features were shipped in this pass. The capability set stayed frozen at the previous level. Deliberate, quality over quantity.

## Decision 20: Lazy-load the cross-encoder, split rerank deps into a build-time flag
**Context:** `FEATURES["reranker_enabled"] = MODE != "public-preview"` only stopped the cross-encoder from loading. `sentence-transformers` was still imported at module scope in `retriever.py`, so torch (~3GB) loaded on every boot regardless of the flag, and the Dockerfile's `poetry install --only main` baked it into every image whether or not that image would ever rerank.
**Decision:** `CrossEncoder` import moved inside `get_cross_encoder()`, so it only runs when actually called. `sentence-transformers` moved to a `rerank` Poetry dependency group, excluded by default. The Dockerfile takes an `INCLUDE_RERANK` build arg: false installs `--only main` (no torch, public-preview/free-tier target), true installs `--only main,rerank` (prod target with reranking).
**Trade-off:** Two image variants instead of one. `MODE=prod` deployments must remember to set `INCLUDE_RERANK=true` at build time or reranking silently has no chance to run (the code checks `FEATURES["reranker_enabled"]` first, so it fails at the `get_cross_encoder()` import, not at boot). Measured result: public-preview image dropped from ~600MB to 119MB, steady-state container RSS 240MB against a 512MB budget.

## Decision 21: Gemini embeddings for public-preview mode, one embeddings client for all call sites
*(Since Sprint 006 the client is the `EmbeddingPort` adapter `adapters/litellm_embeddings.py`, with an ordered fallback list: Decision 27.)*
**Context:** Public-preview mode's embedding model defaulted to `ollama/nomic-embed-text`, which resolves to `localhost:11434`. No cloud host runs an Ollama sidecar, so every embed call in a cloud public-preview deployment would have failed, and three call sites (ingestion, semantic cache, health probe) each picked their own model independently.
**Decision:** Public-preview mode now defaults to `gemini/gemini-embedding-001`. `core/clients/embeddings.py` is the single entry point all three call sites use. The model emits 3072 dims natively; the client requests and renormalizes to 768 to match the existing `VECTOR(768)` schema column, so no migration was needed.
**Trade-off:** `text-embedding-004` is retired and returns 404 on current API keys, ruling it out as a fallback. Truncating a 3072-dim embedding to 768 and renormalizing is not the same as a model trained natively at 768 dims; retrieval quality at the truncated size has not been benchmarked against the untruncated one.
Superseded by the Sprint 000 mode rename (`planning/DECISIONS.md`): the hosted mode is named `public-preview`.

## Decision 22: Disable asyncpg's prepared-statement cache for Neon's pooled endpoint
**Context:** Neon's pooled connection string (the `-pooler` hostname) runs PgBouncer in transaction mode. asyncpg's default behavior is to prepare and cache statements server-side per connection, which PgBouncer's transaction pooling cannot support since a connection can be handed to a different client between statements.
**Decision:** `asyncpg.create_pool()` now passes `statement_cache_size=0`. This disables the client-side prepared-statement cache and makes every query a fresh simple/extended-protocol call, which works against both the pooled and direct Neon endpoints.
**Trade-off:** Losing the prepared-statement cache means Postgres re-parses and re-plans each query instead of reusing a cached plan. For this platform's query patterns (a handful of distinct parameterized queries, not thousands of ad-hoc ones), the overhead is negligible next to embedding and LLM latency.

## Decision 23: Render over Koyeb for the free-tier public-preview deployment
**Context:** Koyeb was the original target platform (CLI installed, secrets flow documented). Koyeb had a platform-side outage during deployment that blocked progress and was unrelated to anything in this codebase.
**Decision:** Switched to Render's free tier, deployed via a `render.yaml` Blueprint (Docker runtime, `/health` check, four secrets prompted at setup rather than committed).
**Trade-off:** Render's free tier spins the instance down after 15 minutes idle and cold-starts on the next request. Same constraint Koyeb's free tier would have had; not a regression, just a different provider absorbing it.
Superseded in part by Decision 25 (Sprint 003): `render.yaml` also holds the secrets `MIGRATION_DATABASE_URL` and, on the UI service, `PREVIEW_API_KEY`. Sprint 005 removed `PREVIEW_API_KEY` and the nginx key injection (ADR-0007): the API service now has `PREVIEW_PRINCIPAL_ID` and the UI service holds no secret.

## Decision 24: Platform base: validated settings, Alembic, `/v1`, one error format, structured logs and traces
**Context:** Every later sprint changes schema, API and config. Without migrations, a versioned API and validated settings, each of those changes is unsafe and unprovable.
**Decision:**
- **Settings:** `core/settings.py` holds a `pydantic-settings` `Settings` class. `config.py` builds its dicts from it and keeps its public names. A bad value, an unknown `MODE`, or `public-preview`/`prod` without `DATABASE_URL` and `REDIS_URL` raises `SettingsError` at import, before the app serves anything. Local mode keeps its Docker Compose defaults. There are no placeholder DSNs.
- **Data:** the schema is owned by Alembic (`migrations/`, DSN from `Settings`, synchronous). Baseline `0001` reproduces the old `schema.sql` with `IF NOT EXISTS`, so on the hosted database it only records the version. Migrations are forward-only (`downgrade` raises). The Docker image runs `alembic upgrade head` before uvicorn. The only table added is `alembic_version`.
- **API:** all product routes are under `/v1` (one `APIRouter(prefix="/v1")`). `/` and `/health` stay unversioned for the platform health check, and `/v1/health` also exists. MCP is at `/v1/mcp/sse` and `/v1/mcp/messages/`. Old paths return 404 in the standard error format. `/v1` is listed in OpenAPI at `/openapi.json`.
- **Errors:** every error is `{"error": {"code", "message", "request_id"}}` (`api/errors.py`). HTTPException (including router 404/405), request validation (422), rate limit and token budget (429), guardrail blocks (400) and unhandled exceptions (500, no stack trace in the body) all use it. Middleware answers through `error_response()`.
- **Observability:** `api/observability.py` writes JSON logs, one object per line, with `request_id` and `trace_id`. The OpenTelemetry SDK instruments FastAPI. An OTLP exporter and its background thread exist only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Every response carries `X-Request-ID` and `X-Trace-ID` (the trace id is the OpenTelemetry trace id).
- **Middleware order** (outermost first): CORS, request id, logging and 500 conversion, latency, FinOps (Sprint 003 inserts auth after latency; Sprint 004 removes the rate limit and token budget middleware, now gateway stages). The request id middleware is outside everything so rejected requests also carry ids.
- **Contract and CI guards:** `docs/openapi.json` is a committed snapshot, and a unit test fails if the app differs (refresh with `scripts/update_openapi.py`). CI also fails on `CREATE TABLE` or `ALTER TABLE` outside `migrations/` (`scripts/check_no_ddl.sh`) and runs gitleaks secret scanning. The schema-drift diff against models is deferred to when models exist.
- **Tests:** the `integration` and `e2e` tiers run against a real Postgres (pgvector) and Redis Stack with fake LLM and embeddings (`tests/fakes.py`). A guard fixture fails any real LLM, embedding or non-loopback network call.
**Trade-off:** `/v1` renames the `endpoint` value stored in new `usage_log` rows (`/v1/search`, not `/search`), so analytics shows old and new names side by side until old rows age out. OpenTelemetry covers FastAPI spans only. Database, Redis and LLM spans wait for the Sprint 005 adapters. Alembic autogenerate and a schema-drift check wait for SQLAlchemy models (`migrations/env.py` `target_metadata` is the seam). mypy is non-strict across the codebase and strict for the new modules.

## Decision 25: Identity from a verified token and row-level security, with a non-privileged app role
**Context:** The caller chose its own namespace, so there was no identity and no isolation (gap 1).
**Decision:** API keys (hashed, prefix-indexed) and JWTs resolve to a principal that belongs to exactly one tenant. Postgres row-level security enforces isolation even if application code forgets a filter. Request-path queries run through `tenant_connection()`. The app connects as `gap_app`, a role that row-level security applies to, and refuses to start as a superuser or `BYPASSRLS` role. Caches, the rate limit (per principal) and the token budget (per tenant) key on identity.
**Trade-off:** Postgres refuses `COPY FROM` into a table with row-level security, so bulk ingest moved from `COPY` to a pipelined `executemany` INSERT. Two connection strings are now needed (`DATABASE_URL` and `MIGRATION_DATABASE_URL`). A JWT must also name an existing, enabled principal of the token's tenant (checked through `auth_lookup_principal`), so disabling a principal takes effect on the next request. Auth costs one indexed lookup plus one `last_used_at` write per request; a short-lived principal cache would remove it but would delay revocation, so it is deferred. OAuth login, per-KB ACLs and key rotation UX are deferred (the seam for token issuers is `core/identity/jwt.py`).

## Decision 26: Gateway core: one `enforce()` for every model, tool and KB call (Sprint 004, ADR-0006)
**Context:** The agent could call any tool, rate limit and budget were middleware that failed open, and nothing recorded what was allowed or denied (gaps 3, 4, 5).
**Decision:** The top-level `gateway/` package. `enforce(ctx, action)` runs principal, boundary, policy, input guardrails, rate and budget in order, writes one `gateway_decisions` row per call, and denies on any exception. The `ExecutionBoundary` is frozen, built once per request from scopes and the tenant's active `policies` version, and can only narrow. Routes, the agent (every LLM and tool call) and the MCP tools call `require()`. A deny is 403 `policy_denied` (400 guardrail, 429 limits, 503 when Redis is down). Rate and budget keep their Redis keys, limits and 429 codes. An agent run that hits a denial ends with a partial, `flagged` answer.
**Data:** migration `0005` adds `policies` (append-only versions, one active per tenant, written by the admin CLI) and `gateway_decisions` (insert-only for the app role, SHA-256 of the input, no text). Both have forced row-level security, and the grants to `gap_app` are explicit (SELECT, and SELECT plus INSERT).
**Trade-off:** decision writes fail closed. If the insert fails on an allow, `enforce()` returns a deny with reason `decision_unrecorded` (503) and the work is not done. A deny stays the deny it was, even if its row cannot be written (ADR-0006). Booking tokens after the work stays best effort, because the tokens are already spent. Every governed call costs one insert, and a request reads the tenant's policy once. The default policy (no row) allows what scopes grant, so a tenant must be given a policy to be restricted. Retention of decision rows is open. OPA, PII redaction, approvals and A2A are deferred behind the `PolicyEngine` seam and the stage list.

## Decision 27: Ports and adapters, an event bus and an agent runtime (Sprint 006, ADRs 0005, 0008, 0009)
**Context:** `litellm`, `redis` and `asyncpg` were imported across routes, services, the gateway and the agent. Changing a provider touched many files, there was no embedding fallback, nothing said which model made a vector (gaps 5 and 6), and an agent run had no identity of its own.
**Decision:** The top-level `ports/` package holds typed `Protocol`s (LLM, chat model, embeddings, knowledge store, cache, object store, event bus, agent runtime). `adapters/` implements them (LiteLLM, Postgres with pgvector, Redis, local disk and S3, in-process bus and runtime). `adapters/registry.py` builds one `Adapters` bundle from `Settings` in the lifespan and puts it on `app.state.adapters`. Providers are imported only in `adapters/`, and an import-lint test enforces it. `documents` rows record `embedding_model` and `embedding_dim`; search reads only the active model, and `/v1/health` counts the stale rest. An ordered embedding fallback refuses a different width. The gateway publishes a CloudEvent per recorded decision. `/v1/agent/query` runs through the `AgentRuntime`, and every decision a run causes carries its `execution_id`.
**Data:** migration `0007` adds the two provenance columns (backfilled from the configured model, then not null), a nullable `gateway_decisions.execution_id`, indexes on both, and the `count_stale_vectors` function (narrow, `SECURITY DEFINER`).
**Trade-off:** a thin layer of interfaces, and one more hop per call. The usage, feedback, analytics and console queries still use `tenant_connection` directly: they are not knowledge data. Run status and the in-process event bus live in memory; durable versions come with the queue (Sprint 007). A fallback that works can leave rows whose model is not the active one, which health reports as stale.

## Decision 28: Durable jobs, the outbox and raw storage (Sprint 007, ADRs 0008, 0009, 0011)
**Context:** Ingestion ran inside the request, agent run status lived in memory, events could be lost, and raw files were not kept.
**Decision:** A `jobs` table is the queue. Workers (`python -m workers`) claim with `FOR UPDATE SKIP LOCKED`, hold a lease, retry with backoff and end `dead` after the last attempt. `POST /v1/ingest` stores the raw bytes in the object store under their SHA-256 (once) and answers 202 with a job; a worker chunks, embeds and stores. Agent runs are jobs too: `JobAgentRuntime` implements `AgentRuntime`, a worker runs the agent and stores the answer, and `/v1/agent/query` waits up to `AGENT_SYNC_WAIT_SECONDS` before it answers 202. `/v1/jobs`, `/v1/agent/runs` read the rows under row-level security. The default event bus is a transactional outbox: events are written in the transaction of the change, and a relay publishes them at least once; consumers dedupe by CloudEvent id.
**Data:** migration `0008` adds `jobs`, `outbox` and `processed_events` (forced row-level security; `gap_app` may select, insert and update) and three narrow SECURITY DEFINER functions (`jobs_claim`, `jobs_tenant_of_execution`, `outbox_pending`).
**Trade-off:** no new service (Postgres is the queue), at the price of polling and a database-sized ceiling. A worker must run, or `EMBEDDED_WORKERS` must be set. Every decision writes an outbox row, and nothing purges the new tables yet (Sprint 008).

## Decision 29: Receipts, retention, the eval gate, a cost cap and metrics (Sprint 008, ADR-0012)
**Context:** A decision row could be edited or removed without a trace, kept forever, and nothing guarded answer quality, cost or visibility.
**Decision:** Each decision row joins a per-tenant hash chain (`prev_hash`, `row_hash`, `chain_position`; head in `chain_heads`). `GET /v1/receipts/{id}` signs a decision and its chain link with Ed25519, and `scripts/verify/receipt.py` checks a receipt or a chain offline. Decision records are purged after `DECISION_RETENTION_DAYS` (90) or a tenant's own value, by a `purge_decisions` job through a SECURITY DEFINER function that leaves a chain checkpoint. A `cost` gateway stage (after `budget`) denies with 429 `cost_cap_exceeded` over a per-tenant daily cap, and with Redis down. `scripts/eval/run_gate.py` runs a fixed suite with the fake LLM against a stored baseline in CI. `/metrics` serves Prometheus text from OpenTelemetry instruments; an optional compose profile runs Prometheus and Grafana.
**Data:** migration `0009` adds the three chain columns, `chain_heads`, `chain_checkpoints`, `eval_runs`, `tenants.retention_days` and four SECURITY DEFINER functions (`decisions_purge_batch`, `retention_due_tenants`, `trust_jobs_by_status`, `trust_outbox_lag`).
**QA fixes:** purge checkpoints are signed with the receipt key and written only by the purge function; retention has a 30-day floor; an unpriced model is costed at the highest known rate (hosted modes refuse to start for one); the cost cap is checked before and booked after a call, so concurrent calls can overshoot it by one call each.
**Trade-off:** decision writes of one tenant are serialized by an advisory lock. The chain is tamper evident, not tamper proof (ADR-0012). `jobs`, `outbox`, `processed_events` and raw files still have no purge (Q27).

## Decision 30: Sandboxed agent runs and tool argument checks (Sprint 009, ADR-0009)
**Context:** An agent run executed in the worker process with the platform's own credentials. Nothing stopped it from calling a model provider directly or reading files, and a policy could allow a tool but not say how it may be called.
**Decision:** `AGENT_RUNTIME=openshell` runs each run in an NVIDIA OpenShell sandbox (Apache-2.0, pinned 0.1.2). The runtime sits behind a small `SandboxDriver` port (`ports/sandbox.py`); the sandbox gets one network route (the gateway), one writable directory and CPU, memory and wall-clock limits. The agent in it (`sandbox_agent/entry.py`) has no model key and no database: it calls `/v1/sandbox/runs/{execution_id}/tools/{name}` and `/model` with a **run token** bound to that run, so `enforce()` decides and records every call. A policy may hold `tool_arguments`, a JSON Schema per tool, and the policy stage denies with `tool_argument_not_allowed`. The sandbox's events (start, exit, refused connections, limits) go to `sandbox_events` and the runs API merges them with the run's decisions by time.
**Data:** migration `0010` adds `sandbox_events` (append-only for the app role), `run_tokens` (hash only, short-lived, revocable), a unique `(id, tenant_id)` on `principals` for the token's foreign key, and the narrow lookup function `auth_lookup_run_token`.
**Trade-off:** the worker host needs the OpenShell gateway, Docker and an image. The agent in the sandbox is a retrieve-then-answer program, not the LangGraph agent. OpenShell logs nothing when it refuses a file read. Verified here on a live 0.1.2 gateway with the Docker driver; the standard images could not be pulled, other drivers and platforms are untested (runbook).

## Current state

Where the system stands after Sprint 009. The decisions above hold the reasons; this section holds the shape.

### Data model (Sprint 003)
Migration `0002` adds identity and tenancy on top of the `0001` baseline.
- **Identity tables:** `tenants(id, slug, name)`, `principals(id, tenant_id, kind user|service|agent, name, disabled_at)`, `api_keys(id, tenant_id, principal_id, prefix unique, secret_hash, scopes[], last_used_at, revoked_at)`, `knowledge_bases(id, tenant_id, slug, description, unique(tenant_id, slug))`.
- **Tenant-owned data:** `documents`, `document_registry` (key `(tenant_id, namespace, document_id)`), `usage_log` and `feedback` have `tenant_id uuid not null`. Existing rows were backfilled to the tenant `default`, which owns the KBs `legal`, `kyc_aml` and `default`. Indexes lead with `tenant_id`; the HNSW and GIN indexes cannot and are unchanged.
- **Row-level security:** policy `tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid` for `USING` and `WITH CHECK`, enabled on the seven tenant-owned tables (and a select-only policy on `tenants`), forced on `documents`, `document_registry`, `usage_log`, `feedback` and `knowledge_bases`. `principals` and `api_keys` are enabled but not forced, so the owner-role lookup functions below can read them. Missing setting means zero rows.
- **The one bypass:** `auth_lookup_key(prefix)`, `auth_touch_key(key_id)` and (migration `0003`) `auth_lookup_principal(principal_id, tenant_id)` are `SECURITY DEFINER` functions owned by the migration role. They run before a tenant is known, return only the columns needed to verify a key, and are the only way the app role reads `api_keys` across tenants.
- **Roles:** `gap_app` (`LOGIN NOSUPERUSER NOBYPASSRLS`) is the app. The owner role migrates. Least privilege (migration `0004`): the app reads `api_keys`, `principals`, `tenants` and `knowledge_bases` and cannot write them (keys and KBs are admin-CLI work; `last_used_at` goes through `auth_touch_key`). It writes only `documents`, `document_registry`, `usage_log` and `feedback`. No default privileges: a migration that adds a table grants the app role what it needs, explicitly. Migrations create no roles or passwords.

### API and authentication (Sprint 003)
- **Order of middleware**, outermost first: CORS, request id, logging, latency, **auth**, FinOps (rate limit and token budget moved into the gateway in Sprint 004). Auth verifies the bearer credential and puts a frozen `Principal(id, tenant_id, kind, scopes)` on `request.state`, so the gateway keys on it and an unauthenticated request never reaches a route. Public: `/`, `/health`, `/v1/health`, `/docs`, `/redoc`, `/openapi.json`.
- **Per route:** `Depends(require_scope(Scope.X))` declares the scope and returns the principal; handlers take `tenant_id` only from it. `require_kb()` resolves a KB slug in the caller's tenant (404 `kb_not_found`, one body for foreign and missing).
- **Agent and MCP:** the agent run carries the gateway enforcement context (its boundary holds the tenant) in the LangGraph run config (`configurable`), never as a tool argument the model could set. MCP requires the same bearer credential; the principal is bound per message and the SDK ties each SSE session to the principal that opened it.
- **Errors:** 401 `unauthorized` (one generic message), 403 `forbidden` (names the scope), 404 `kb_not_found`, 503 `service_unavailable` if authentication itself cannot run (fail closed).

### Gateway data (Sprint 004)
- **Tables:** migration `0005` adds `policies` (append-only versions, one active per tenant) and `gateway_decisions` (one row per `enforce()` call, SHA-256 of the input, no text). Forced row-level security on both. `gap_app` gets SELECT on `policies` and SELECT, INSERT on `gateway_decisions`.
- **Migration chain:** `0001` baseline, `0002` identity and tenancy, `0003` principal lookup, `0004` app-role least privilege, `0005` gateway. All forward-only.
- **Governance path:** every model, tool and KB call goes through `gateway.enforce()` (Decision 26, ADR-0006). The rate limit and token budget are stages in `gateway/stages.py`, not middleware.

### Ports and adapters (Sprint 006)
- **Layout:** `ports/` (contracts), `adapters/` (providers), `adapters/registry.py` (composition root), `app.state.adapters` (the bundle), `app.state.gateway_runtime` (`pool`, `cache`, `events`).
- **Embedding provenance:** `documents.embedding_model` and `embedding_dim` are not null. Search (text and vector) filters on the model and dimension of the query vector. The exact cache key and semantic cache entries carry the model.
- **Migration chain:** `0001` to `0005` as above, `0006` preview principal lookup, `0007` embedding and run provenance. All forward-only.
- **Tests:** `tests/contracts/` runs one suite per port against every adapter. The app in the integration and e2e tiers is built by the registry with the fakes the test asks for.

### Trust (Sprint 008)
- **Layout:** `gateway/chain.py` (canonical JSON, hashes, chain check), `gateway/receipts.py` (keyring, sign, verify), `gateway/record.py` (chained write), `core/metrics.py`, `api/middleware/metrics.py`, `api/routers/receipts.py`, `api/routers/trust.py`, `workers/handlers/purge.py`, `workers/scheduler.py`, `workers/metrics_server.py`, `scripts/eval/`, `scripts/verify/receipt.py`, `docker/observability/`.
- **Routes:** `GET /v1/receipts/{id}`, `GET /v1/receipts/keys`, `POST /v1/receipts/verify`, `GET /v1/trust/summary` (all `audit:read`), `GET /metrics` (open when `METRICS_PUBLIC`, else `admin`).
- **Migration chain:** `0009` trust baseline.

### Sandboxed runs (Sprint 009)
- **Layout:** `ports/sandbox.py` (the driver contract), `adapters/openshell_runtime.py` (the `AgentRuntime`), `adapters/openshell_driver.py` (the OpenShell SDK driver, imported lazily), `adapters/openshell_events.py` and `adapters/sandbox_events.py` (turn and write events), `core/identity/run_tokens.py`, `api/routers/sandbox.py`, `sandbox_agent/` (the program that runs inside), `tests/fake_sandbox.py` (the test double), `scripts/verify/openshell.sh` and `docs/runbooks/openshell.md`.
- **Routes:** `POST /v1/sandbox/runs/{execution_id}/tools/{name}` and `/model`, which accept a run token only. `GET /v1/agent/runs/{execution_id}` returns `sandbox_events` and `timeline`.
- **Where it runs:** the API queues the run as before. The worker builds the sandbox runtime (`build_local_runtime`), so `AGENT_RUNTIME=openshell` needs a gateway, Docker and a workload image on the worker host.
- **Migration chain:** `0010` sandbox events and run tokens.

### Jobs and the outbox (Sprint 007)
- **Layout:** `core/database/jobs.py` (queue SQL), `workers/` (`loop.py` the worker, `handlers/` ingest and agent run, `embedded.py`, `__main__.py`), `adapters/job_runtime.py` (queued runtime), `adapters/pg_outbox_events.py` (outbox bus, relay, idempotent consumer).
- **Routes:** `POST /v1/ingest` (202), `GET /v1/jobs`, `GET /v1/jobs/{id}`, `GET /v1/agent/runs`, `GET /v1/agent/runs/{execution_id}`; `POST /v1/agent/query` may answer 202.
- **Run it:** `docker compose up -d postgres redis worker`, or `poetry run python -m workers`, or `EMBEDDED_WORKERS=1` in the API process.
- **Visibility:** jobs carry `namespace` and `principal_id`. Job and run routes show only the knowledge bases the boundary allows; `/v1/agent/runs` shows a caller without `audit:read` only its own runs (ADR-0011).
- **Migration chain:** `0008` jobs, outbox, processed events.

### Kafka event bus (Sprint 010)
- **Layout:** `adapters/kafka_event_bus.py` (the adapter, the only `aiokafka` import), `tests/fake_kafka.py` (the in-memory broker), `docker-compose.yml` profile `kafka` (Redpanda and a topic job), `scripts/verify/kafka.sh`, `docs/runbooks/kafka.md`.
- **Flow:** the API writes the outbox in the decision's transaction, as before. With `EVENT_BUS=kafka` the relay publishes the rows to `platform.<type without version>` keyed by tenant id, in CloudEvents binary mode. Kafka is never reached inside a request. A consumer group handler is deduped by CloudEvent id through `processed_events`, and a message that keeps failing goes to `<topic>.dlq` (ADR-0008).
- **Switching:** `EVENT_BUS=outbox` again needs no migration. There is none in this sprint (the chain still ends at `0010`).

## Known Open Gaps (Deferred by Design)

- **Real-time citation content validation:** The code validates that a `chunk_id` exists in the database, but does not run an LLM check on the live path to prove the chunk content strictly entails the sentence. Doing this synchronously would add 300ms+ latency and double LLM token cost per request. Offline DeepEval faithfulness scoring measures citation quality in batch. Live citation validation is deferred.
- **Monthly aggregate budget caps:** Daily LLM spend is tracked and capped in Redis to prevent catastrophic runaway costs. Monthly aggregation and billing tier logic require persistent DB rollups and accounting rules, which are deferred because daily caps mitigate 99% of financial risk.
- **Event-driven CDC cache invalidation:** Cache invalidation uses TTL=3600s. Real-time CDC (Change Data Capture) via Postgres triggers or Redis Pub/Sub would immediately invalidate cached queries when a document changes, but adds background worker complexity. Because compliance documents update quarterly at most, TTL expiry combined with SHA-256 document lifecycle management is an acceptable tradeoff. CDC invalidation is deferred.
- **`fetch_full_document` tool:** For when a 500-character chunk is not enough surrounding context. Needs to be confirmed against the actual `documents` table schema before building to ensure reassembly by chunk order sorts on how `chunk_index` is actually stored (e.g. inside a metadata JSON column), not row insertion order. Deferred to future work.
- **Retention of the other tables:** decision records are purged (Sprint 008, Q7 closed). `jobs`, `outbox`, `processed_events` and raw files have no purge yet (Q27). The chain is not anchored outside Postgres (Q29).
- **Stale vectors are not re-embedded:** after an `EMBED_MODEL` change old chunks are ignored and counted (`stale_vectors`); the queue now exists, so a re-embedding job can be built on it (not scheduled).
- **Raw files are stored, never read back by a person:** the object store keeps every upload by SHA-256 and nothing deletes them. The live MinIO run is `scripts/verify/minio.sh`.
- **Old chunks cite `unknown`:** chunks ingested before Sprint 002 have no `source_filename` in metadata until they are re-ingested.
- **Closed:** the persistent-usage question is answered by Decision 18 (`usage_log`), and the no-identity gap by Decisions 25 and 26.

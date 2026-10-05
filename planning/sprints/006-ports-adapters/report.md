# Sprint 006: Report

Built, tested and verified in this container, except what is marked "not verified here". Nothing was committed or pushed. Evidence is in `evidence/` and is captured command output.

## 1. Acceptance

| Check | Status | Evidence |
|---|---|---|
| **A1** ruff, mypy (strict on `ports/` and `adapters/`), DDL guard, unit tests | **Done.** ruff clean on `api core gateway ports adapters tests scripts/e2e`; mypy clean on 110 files; DDL guard OK; unit 543 passed, 0 failed | `ruff.txt`, `mypy.txt`, `pytest-unit.txt` |
| **A2** int + e2e + contracts: 0 failed, 0 skipped except the MinIO skip | **Done, with the documented skip.** 541 passed, 0 failed, 10 skipped (all are the live MinIO parameter of the object store contract; the image cannot be pulled here). Earlier tests pass; the assertions that had to change are listed in section 4 | `pytest-int-e2e.txt` |
| **A3** no `litellm`, `langchain_litellm`, `redis` imports in `api core gateway`; import-lint passes | **Done.** The grep finds nothing. `asyncpg` appears only in `core/database/` and `core/identity/store.py`. 93 import-lint tests pass, including an injected violation for each banned module, lazy imports and `importlib` | `grep-imports.txt` |
| **A4** each port has a contract suite on at least 2 implementations | **Done for 7 of 8 ports.** LLM and chat (fake, LiteLLM adapter with the SDK call replaced, and the adapter under the network guard), embeddings (fake, LiteLLM adapter), knowledge store (Postgres as `gap_app`, in-memory fake), cache (Redis Stack, in-memory fake), object store (local disk, S3 adapter over a fake client, live MinIO skipped), event bus (in-process, recording fake). **AgentRuntime has one implementation** (in-process) until the workers in 007 and OpenShell in 009; its suite is ready for them | test ids in `pytest-int-e2e.txt` (`tests/contracts/...[postgres]`, `[fake]`, `[redis]`, ...) |
| **A5** migration 0007 on data: counts kept, every row has model and dimension | **Done.** From 0005 with two tenants: 5 documents before and after, every row `('ollama/nomic-embed-text', 768)`, no nulls, `NOT NULL` set, both indexes, nullable `execution_id`. Also run as a non-superuser owner under forced row-level security (the hosted case), through all migrations | `migrate.txt` |
| **A6** live run: ingest, search, change `EMBED_MODEL`, restart: no old chunk found, `stale_vectors > 0` | **Done, with fake providers.** Real API process restarted three times on real Postgres and Redis. Model A: found, `stale_vectors` 0. Model B: 404 in hybrid, vector and text modes, `stale_vectors` 1, rows kept. Model A again: found. There are no API keys, so the LLM and embeddings behind the ports are the fakes | `live-stale.txt` |
| **A7** ADR-0005 updated, ADR-0008, ADR-0009, docs, OpenAPI refreshed, no secrets | **Done.** ADR-0005 rewritten, ADR-0008 and ADR-0009 new, ADR index, ADR-0006 note, `ARCHITECTURE.md` (Decision 27, current state, gaps), `AGENTS.md` (repo map, ports rule, how to add a provider), `.env.example`, `README.md`, `CONTENT_STYLE.md` glossary, CHANGELOG, STATE. `docs/openapi.json` regenerated (`stale_vectors`, `execution_id`, `run_status`), snapshot test passes. A scan of the new files finds no secret | this report, `git diff` |
| **A8** requirement to tests table, every moved function | **Done**, sections 2 and 3 below | this report |
| **A9** EventBus contract on the in-process adapter; one event per decision, no input text | **Done.** 17 contract tests on two buses. E2E: every decision row of a run of ingest, search, a policy deny and an agent query has exactly one event; the payload equals the row's verdict fields; the handler sees the uncommitted row through `tx` (same transaction); the query text and the words of it are not in any event; a bus that raises turns an allow into 503 `decision_unrecorded` and rolls the row back | `eventbus.txt` |
| **A10** AgentRuntime contract; `/v1/agent/query` goes through it; decisions carry `execution_id` | **Done.** 14 contract tests (start, status, wait, stop, stop during a tool call, cleanup, bounded history). E2E: one run, one execution id on every decision of the request (entry, model, tool, KB); an ingest and a search carry none; stopping the real LangGraph agent while it is in `retrieve_chunks` cancels the tool; a client disconnect stops the run; a crashed run is the same 500 and a `failed` status | `agent-runtime.txt` |
| **A11** Agent runs page shows `execution_id` and status; Vitest test; Playwright green | **Done.** New columns and a status and id panel; 5 Vitest tests; 1 new Playwright test (a real agent ask, then the page shows "Finished" and a UUID). `tokens:check`, lint, `tsc`, build, chunk report and copy check pass. 167 Vitest (was 162), 71 Playwright (was 70) | `ui-checks.txt`, `ui-vitest.txt`, `ui-runs-vitest.txt`, `ui-build.txt`, `ui-playwright.txt` |

Not verified here: the live MinIO run of the object store contract (`scripts/verify/minio.sh`, Q B12), the hosted migration, a Docker image build, CI on GitHub, a human visual review of the Agent runs page, and any real provider.

## 2. Requirement to tests

| Requirement | Where it is tested |
|---|---|
| 1 `ports/` | `tests/contracts/*` (the Protocols are exercised by every suite); mypy strict on `ports/` |
| 2 `adapters/` | `tests/contracts/*` per port; `tests/unit/test_embedding_adapter.py` (fallback order, refusal, truncation); `tests/unit/test_llm.py` (LiteLLM adapter through the service, 14 tests, assertions unchanged); `tests/integration/test_retrieval.py`, `test_ingestion_lifecycle.py` (Postgres adapter); `tests/integration/test_cache_tenancy.py` (Redis adapter) |
| 3 composition root | `tests/unit/test_registry.py` (10: defaults, settings drive providers, overrides, unknown override refused, S3 selected, S3 settings validated); every e2e test builds the app through it; `tests/e2e/test_ports_e2e.py` builds second apps |
| 4 fakes are adapters | `tests/fakes.py`, `tests/db_fixtures.py`, `tests/e2e/conftest.py::adapter_overrides`; `tests/unit/test_network_guard.py`; the network-guard e2e and integration tests keep the real LiteLLM adapters under the guard |
| 5 embedding provenance (0007) | `tests/integration/test_migration_0007.py` (6); `test_ports_e2e.py::test_ingested_chunks_record_...`, `::test_changing_the_embedding_model_makes_old_chunks_stale_not_wrong`, `::test_health_reports_no_stale_vectors_...`, `::test_the_semantic_cache_is_not_shared_across_embedding_models`; knowledge contract `test_vectors_of_another_model_or_dimension_are_ignored_and_counted_as_stale`; `test_cache_tenancy.py::test_the_semantic_cache_is_isolated_per_embedding_model` |
| 6 embedding fallback | `test_embedding_adapter.py` (9); `test_ports_e2e.py::test_the_fallback_embeds_when_the_primary_fails...` and `::test_a_fallback_with_another_dimension_is_refused_and_logged`; embeddings contract (dimension check on the fake and the adapter) |
| 7 import-lint | `tests/unit/test_import_lint_ports.py` (49), `test_gateway_import_lint.py`, `test_gateway_gate_calls.py` |
| 8 contract tests | `tests/contracts/`: runtime 14, cache 25, embeddings 9, event bus 17, knowledge store 20, LLM and chat 12, object store 30 (10 skipped for MinIO) |
| 9 EventBus | `test_event_bus_contract.py`, `tests/unit/test_decision_event.py`, `test_ports_e2e.py` (3 event tests) |
| 10 AgentRuntime | `test_agent_runtime_contract.py`, `test_ports_e2e.py` (6 runtime tests), `tests/unit/test_agent_tools.py::test_agent_query_initializes_reducer_lists_and_runs_graph` (route through the runtime, unchanged assertions) |
| 11 UI touch | `ui/src/features/runs/runs-page.test.tsx`, `ui/e2e/governance.spec.ts` (new test), `test_ports_e2e.py::test_the_console_shows_a_runs_execution_id_...` |
| Fail closed, bugs in own code | a bus that raises (`test_a_failing_event_bus_fails_the_decision_closed`), a runner that raises (500 and `failed`), a cache that raises (`dependency_unavailable`, `CacheUnavailable` contract), a provider refusal (502 or 500, nothing stored), the existing stage-exception tests |

## 3. Moved functions (from to)

- `api/services/llm.py`: the `litellm.acompletion` call, the finish reason, the token counts and the price calculation to `adapters/litellm_llm.py::LitellmLLM.complete`. `generate_with_citations(llm, query, chunks, model)` and `generate_with_routing` stay, now taking the port first. The rate-limit retry stays in the service.
- `api/agent/models.py`: `chat_model` to `adapters/litellm_chat.py::LitellmChat.chat_model`; `completion_cost` to `LitellmChat.cost`. Only the token budgets stay.
- `core/clients/embeddings.py` (deleted): `aembed_texts`, `_truncates`, `_renormalize` to `adapters/litellm_embeddings.py::LitellmEmbeddings.embed`, `_truncates`, `_renormalize`.
- `core/ingestion/embedders.py::embed_chunks`: now takes the port and also returns the model and dimension.
- `api/services/cache.py`: `get_redis`, `close_redis` to `RedisCache.__init__`, `close`; `redis_health` to `cache_health` (over `CachePort.ping`); `_ft_create`, `create_semantic_cache_index` to `RedisCache._ft_create`, `ensure_semantic_index`; the `FT.SEARCH` in `semantic_cache_lookup` to `RedisCache.semantic_lookup`; the pipeline in `semantic_cache_store` to `RedisCache.semantic_store`; `embed_query` to `api/services/embedding.py`. The exact-cache `get_cached_response`, `set_cached_response` and the key stay, over `CachePort`.
- `gateway/limits.py`: the Redis calls in `check_rate`, `check_budget`, `record_usage`, `read_budget_used` to `CachePort.incr` and `get`. Keys, limits, messages and headers unchanged.
- `api/web_edge/{session,auth,routes}.py`: `redis.set/get/expire/delete/incr` to the same calls on `CachePort`.
- `api/services/retriever.py`: `retrieve_bm25` to `PgKnowledgeStore.search_bm25`; `retrieve_vector` to `search_vector`; `_parse_metadata`, `BM25_OR_THRESHOLD` to `adapters/pg_knowledge.py`. `rrf_merge`, `rerank` and `retrieve` stay; `retrieve` takes the store and an `Embeddings` result.
- `core/ingestion/lifecycle.py`: `check_document_status` to `document_status`; `delete_document_chunks` to `delete_document`; `register_document` to `register_document`. `compute_content_hash` stays.
- `core/database/bulk_ops.py` (deleted): `bulk_insert` to `insert_chunks`.
- `core/pipeline/db_ingest.py::ingestion_pipeline`: takes `store` and `embeddings` instead of a pool (standalone scripts use `scripts/corpus/_standalone.py`).
- `api/routers/docs.py` listing SQL to `list_documents`; `api/routers/config.py`, `api/auth.py::require_kb`, the agent tools and the MCP tools and resources knowledge-base reads to `list_knowledge_bases` and `kb_exists`.
- `api/agent/router.py`: `graph.ainvoke`, the recursion limit and the `GraphRecursionError` handling to `api/agent/runner.py` (`make_agent_runner`, `recursion_limit_for`), run by `adapters/inprocess_runtime.py`.
- `api/observability.py`: `litellm.suppress_debug_info` to `adapters/litellm_llm.py`.
- `api/main.py`: the Redis and graph start-up to the registry and `_lifespan`. `GatewayRuntime(pool, get_redis)` is now `GatewayRuntime(pool, cache, events)`.
- `gateway/record.py::write_decision`: now returns the id, writes `execution_id` and publishes the event.
- Callers updated: `scripts/e2e/serve.py`, `scripts/lab_7.5_deep_eval_v5.py`, `scripts/corpus/{build_kyc_corpus,ingest_compliance_corpus,build_corpus,ingest_real_corpus}.py`.

## 4. Files changed

- **New:** `ports/` (9 modules), `adapters/` (11 modules incl. `registry.py`), `api/agent/runner.py`, `api/services/{embedding,run_status}.py`, `migrations/versions/0007_embedding_provenance.py`, `docs/adr/{0008-event-bus,0009-agent-runtime}.md`, `scripts/verify/{minio.sh,stale_vectors.py,serve_fakes.py,migration_0007.py}`, `scripts/corpus/_standalone.py`, `tests/contracts/` (7 suites), `tests/e2e/test_ports_e2e.py`, `tests/integration/test_migration_0007.py`, `tests/unit/{test_import_lint_ports,test_registry,test_embedding_adapter,test_decision_event}.py`, `ui/src/features/runs/{run-status.ts,runs-page.test.tsx}`.
- **Deleted:** `core/clients/embeddings.py`, `core/database/bulk_ops.py` (both empty after the move).
- **Changed (product):** routes (`search`, `ingest`, `docs`, `config`, `health`, `console`, agent router), `api/main.py`, `api/auth.py`, `api/dependencies.py`, `api/mcp/*`, `api/agent/{graph,tools,models}.py`, `api/web_edge/*`, `api/services/{cache,llm,retriever}.py`, `api/models/{schemas,console}.py`, `gateway/{types,limits,record}.py`, `core/{settings,ingestion/*,pipeline/db_ingest,database/*}.py`, `config.py` (comments).
- **Changed (other):** `pyproject.toml` (boto3, mypy and coverage scope, strict override), `poetry.lock` (content hash only: boto3 was already locked), `Dockerfile` (copies `ports/` and `adapters/`), `.github/workflows/{tests,frontend}.yml`, `docs/openapi.json`, `ui/src/api/schema.d.ts`, `ui/src/features/runs/runs-page.tsx`, `ui/e2e/governance.spec.ts`.
- **Tests changed.** Fixtures, patch points and call signatures only, with these exceptions where the assertion itself had to change:
  1. `tests/e2e/test_console_api.py` (2 places) and `test_console_requests_api.py` (1): the decision field set now includes `execution_id` and `run_status` (brief: decisions gain `execution_id`).
  2. `tests/integration/test_migrations.py` (2 places): head revision `0006` is now `0007`.
  3. `tests/unit/test_gateway_gate_calls.py`: "the model seam is the only agent or MCP module that imports a provider" is now "no agent or MCP module imports a provider; the adapters do".
  4. `tests/unit/test_network_guard.py` (2 tests): the fakes are ports now, so they are called as ports.
  5. `tests/unit/test_gateway_enforce.py`: the "client cannot be created" test breaks the cache port instead of a `get_redis` getter; same expectation.
  6. `tests/unit/test_gateway_packaging.py`: also asserts `ports` and `adapters` are copied into the image and in the lint and mypy scope.
  No test was weakened, skipped or deleted. `tests/unit/test_llm.py` keeps its 14 tests and assertions, now through the real LiteLLM adapter with the SDK call replaced.

## 5. Test numbers

- Backend: **1084 passed, 0 failed, 10 skipped** (baseline 875 passed, 0 skipped). Unit 543. Integration, e2e and contracts 541 passed. The 10 skips are the live MinIO parameter, each with a reason.
- New backend tests: 219 collected (127 contract tests, 10 of them the skipped MinIO parameter; 70 unit; 6 for migration 0007; 15 ports e2e; 1 cache), so 209 more pass than the baseline.
- Frontend: **167 Vitest passed** (162 before), **71 Playwright passed** (70 before). Lint, `tsc`, tokens check, build, chunk report and copy check pass.

## 6. Problems and fixes

- The old tests patched `litellm` and read `app.state.redis`. Fakes now go behind the ports through `create_app(adapter_overrides=...)`; a test that asks for `fake_llm` or `fake_embeddings` gets the app built with them, and a test that asks for none keeps the real LiteLLM adapters under the network guard (the guard tests rely on that). `redis_raw` replaces `app.state.redis` where tests look at keys.
- The Dockerfile copied only `api`, `core` and `gateway`: the image would not have started. Fixed, and a packaging test now guards it.
- CI failed the job on any skipped test. It now allows only the MinIO live-run skip.
- An empty embedding-model tag broke the Redis semantic filter (a syntax error that the cache swallowed): the adapter uses a placeholder.
- The `0007` backfill and `count_stale_vectors` loop over tenants and set `app.tenant_id`, because an owner role that is subject to forced row-level security sees no rows otherwise. A test runs every migration as such a role.
- Search originally filtered only the vector side. A stale chunk still matched by text in hybrid mode, so the text search filters on the model too ("search returns nothing for them").
- `litellm.completion_cost` rejects the token arguments the old helper passed, so the agent's best-effort cost always failed silently. Moved as it was; Q18.

## 7. Skipped items and why

- **Live MinIO run:** the image cannot be pulled here. `scripts/verify/minio.sh` is written and the S3 adapter passed the same contract against an in-memory client. Not verified here.
- **A second AgentRuntime implementation:** none exists until 007 and 009. The suite is ready.
- **The usage, feedback, analytics, console and MCP ingestion-status and cost queries** still use `tenant_connection(DbPool, ...)` in their routers. They read `usage_log`, `feedback` and `gateway_decisions`, not knowledge data, and they import no driver. The brief named "docs/analytics queries" for `pg_knowledge`; the documents listing moved, the usage analytics did not (decision below).
- **Per-adapter OTel spans, a re-embedding job, an HTTP stop endpoint:** out of scope, as the brief says.

## 8. Decisions and deferred costs

- **`Completion` has `finish_reason`, and `complete()` takes `response_format`.** The synthesis call needs both (JSON output, and the truncation check). `temperature` defaults to None and is not sent unless given, so the provider call is unchanged.
- **Hybrid fusion stays in `retrieve()`.** The port has `search_bm25` and `search_vector`; RRF and the cross-encoder are service logic, shared by every store.
- **Both searches take the model and dimension.** The caller passes those of the query vector (`Embeddings.model`), so a query embedded by a fallback only meets rows embedded by that fallback. Rows made by a fallback are recorded under the fallback's name, so health reports them as not current. Deferred: the re-embedding job.
- **The exact cache key and the semantic entries carry the embedding model**, so an `EMBED_MODEL` change never serves an old answer.
- **`execution_id` is allocated before the first gateway check**, so entry decisions carry it. A request denied before the run starts has decisions with an execution id and no run; the console shows "Not tracked".
- **The event is published inside the decision's transaction** (`tx` is the connection). An outbox can then commit with the decision. The in-process bus swallows a subscriber's error; a bus that raises makes the allow a 503 `decision_unrecorded`. Deferred cost: a subscriber that fails a database call through `tx` aborts the transaction, which fails closed.
- **`wait` is a fifth `AgentRuntime` method.** A synchronous route needs the result. Status history is 1000 runs in memory (Q19).
- **`count_stale_vectors` visits every tenant** on each health call (Q20).
- **Identity stays outside the ports**, as the brief says; the reason is in ADR-0005.
- **Migration `0007` is one migration** (add, backfill, not null) and needs the migration and the new image deployed together (Q17).
- **`EMBED_FALLBACK_MODELS` is empty by default** (Q16): no provider was chosen and none can be tested without a key.
- **Dependency:** `boto3` (sync, run in worker threads), not `aioboto3`. `poetry.lock` changed only its content hash.

## 9. STATE and CHANGELOG

Both updated (`planning/STATE.md`, `CHANGELOG.md`). `planning/QUESTIONS.md` has Q16 to Q20, B12 and B13. No other planning file was touched. No commit commands here: the Architect writes them.

## 10. QA follow-ups (Architect)
- **M1:** a decision row is never lost because of the bus. A deny publishes inside a savepoint and keeps its row. An allow still fails closed with 503. Tested.
- **M3:** the 0007 backfill uses `vector_dims(embedding)`, and it refuses a width mismatch before it changes anything. Tested.
- **M2:** the hosted checklist says to deploy 0007 and the new image together.
- **L5:** the network-guard tests patch `litellm` again.
- **L6:** `scripts/check_skips.py` lets CI accept only the 10 live-MinIO skips.
- **L7:** a test fixes the list of `/v1` routes exempt from auth.
- **L9:** ADR-0005 notes that the lab scripts are outside the lint.
- **Accepted:** L4, L8 and L10 (see `qa-review.md`).

## 11. Architect re-run
- **Backend:** 1097 passed, 10 skipped. All 10 skips are the live MinIO run. ruff (in-scope paths) and mypy (110 files) are clean, and the DDL guard is OK.
- **UI:** 167 Vitest tests and 71 Playwright tests pass.

## 12. Commit blocks
These are in `planning/COMMIT_PLAN.md` under Sprint 006.

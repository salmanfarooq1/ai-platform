# Sprint 006: Ports and adapters: Requirements

## Goal
Every external provider (LLM, chat model for the agent, embeddings, knowledge store, cache, object store) sits behind a typed port. Swapping one is a config change. Vectors record the model and dimension that produced them.

## Why it matters
Strict rules 9 and 12, and gaps 5–6. Today `litellm`, `asyncpg` and `redis` are imported across routes, services and the gateway. Changing a provider touches many files, and there is no embedding fallback.

## Scope
1. **`ports/` package:** Protocols plus the typed results.
   - `LLMPort.complete(messages, *, model, max_tokens, temperature) -> Completion(text, model, tokens_in, tokens_out, cost_usd)`
   - `ChatModelPort` for the agent: tool binding plus an invoke that returns tool calls or text
   - `EmbeddingPort.embed(texts) -> Embeddings(vectors, model, dim)`
   - `KnowledgeStore`: hybrid search, insert chunks, delete document, list documents, registry ops, always given a tenant context
   - `CachePort`: get, set, incr with TTL, plus the semantic lookup and store
   - `ObjectStore`: `put(bytes) -> sha256 key`, `get(key)`, `exists(key)`, with content addressing
2. **`adapters/` package:**
   - `litellm_llm`, `litellm_chat`, `litellm_embeddings` (with an ordered fallback list per mode)
   - `pg_knowledge` (moves the SQL from `retriever.py`, `lifecycle.py`, `bulk_ops.py`, `db_ingest.py` and the docs/analytics queries)
   - `redis_cache` (cache plus limits)
   - `local_object_store` (filesystem)
   - `s3_object_store` (S3 API, for R2 or MinIO), tested against MinIO if the image is pullable, otherwise behind a contract test (record which)
3. **Composition root:** `adapters/registry.py` builds one `Adapters` bundle from `Settings` at startup and puts it on `app.state`. Routes, gateway, agent and MCP receive ports, never SDKs.
4. **Test fakes become adapters:** `tests/fakes.py` implements the ports, and the test app is built with fake adapters through the registry. Monkeypatching `litellm` stays only in the network-guard tests.
5. **Embedding provenance (migration 0007):**
   - Add `embedding_model text not null` and `embedding_dim int not null` to `documents`, backfilled from the current setting. Plus an index.
   - Retrieval only compares vectors with the active model and dimension. Rows from another model are ignored and counted in `/v1/health` as `stale_vectors`.
6. **Embedding fallback:** if the primary fails, the next provider in the list is tried. If its dimension differs from the active one, it is refused, which is fail closed and logged. Tested.
7. **Import-lint, enforced by tests:**
   - `litellm`, `langchain_litellm` and `boto3`/`aioboto3` only in `adapters/`.
   - `redis` only in `adapters/` (the gateway limits use `CachePort`).
   - `asyncpg` only in `adapters/`, `core/database/` and `core/identity/store.py`. Identity stays where it is, with the reason recorded.
8. **Contract tests:** one shared test suite per port, run against every adapter that implements it (real vs fake). The fake and the real adapter must pass the same contract.

9. **EventBus port (ADR-0008).** `EventBus.publish(event)` and `subscribe(type, handler)`. Events are CloudEvents 1.0 (`id`, `source`, `type`, `specversion`, `time`, `subject`, `tenantid` extension, `data`).
   - The default adapter is in-process and runs handlers in the same transaction context the caller gives.
   - The gateway publishes `platform.gateway.decision.v1` after each recorded decision. The payload carries the decision id and verdict, never input text.
   - A contract test runs against every EventBus adapter. The Kafka adapter in 010 and the outbox in 007 must pass it.
10. **AgentRuntime port (ADR-0009).** `start(spec) -> RunHandle`, `status(run_id)`, `stop(run_id)`, `cleanup(run_id)`. Every run has an `execution_id` that is written into each `gateway_decisions` row the run causes (nullable column, in the same migration).
   - The default adapter is in-process and wraps the existing LangGraph agent.
   - `/v1/agent/query` goes through it.
   - A contract test covers start, status, stop and cleanup, including a stop during a tool call.
   - OpenShell (009) and the workers (007) plug in behind it.
11. **Small UI touch:** the Agent runs page shows `execution_id` and the run status from the runtime.

## Out of scope
Queue, jobs and the outbox (007). New providers beyond the existing modes. OTel spans per adapter (allowed if cheap, but not required).

## Rules
9, 12, plus all previous rules. No behaviour change visible to API clients except the new health field.

## Edge cases
- The hosted DB has vectors with no model column: the backfill uses the configured public-preview model.
- Changing `EMBED_MODEL` in config makes all old rows stale: search returns nothing for them rather than wrong matches, and health shows the count.
- An object store `put` of the same bytes twice gives the same key, written once.

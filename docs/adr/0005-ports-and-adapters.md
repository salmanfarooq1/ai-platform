# ADR 0005: Ports and adapters for external providers

**Status:** Accepted. Updated in Sprint 006 (the registry and the composition root, the ports as built, the import-lint rules).

## Context
- Before Sprint 006 providers were chosen by LiteLLM model strings and clients spread across `api/services/llm.py`, `core/clients/embeddings.py`, `api/agent/models.py`, `api/services/cache.py`, and the SQL in `api/services/retriever.py`, `core/ingestion/lifecycle.py` and `core/database/bulk_ops.py`. `litellm`, `redis` and `asyncpg` were imported across routes, services and the gateway.
- There was no embedding fallback.
- The vector column is fixed at `VECTOR(768)`, and nothing recorded which model produced each vector.

## Decision
- **Ports** are Python `Protocol`s with frozen dataclasses for results, in the top-level `ports/` package. They import no provider SDK. As built:

  | Port | Methods | Adapters |
  |---|---|---|
  | `LLMPort` | `complete(messages, *, model, max_tokens, temperature, response_format) -> Completion` | `litellm_llm` |
  | `ChatModelPort` | `chat_model(max_tokens) -> ChatModel` (`bind_tools`, `ainvoke -> AIMessage`), `cost` | `litellm_chat` |
  | `EmbeddingPort` | `embed(texts) -> Embeddings(vectors, model, dim)`, `active_model`, `active_dim` | `litellm_embeddings` (ordered fallbacks) |
  | `KnowledgeStore` | `kb_exists`, `list_knowledge_bases`, `search_bm25`, `search_vector`, `insert_chunks`, `delete_document`, `document_status`, `register_document`, `list_documents`, `count_stale_vectors` | `pg_knowledge` |
  | `CachePort` | `get`, `set`, `incr`, `expire`, `delete`, `ping`, semantic `lookup` and `store`, `ensure_semantic_index`, `close` | `redis_cache` |
  | `ObjectStore` | `put(bytes) -> sha256 key`, `get`, `exists` | `local_object_store`, `s3_object_store` |
  | `EventBus` | `publish(event, tx)`, `subscribe(type, handler)` (ADR-0008) | `inprocess_events` |
  | `AgentRuntime` | `start`, `status`, `wait`, `stop`, `cleanup` (ADR-0009) | `inprocess_runtime` |

  Every `KnowledgeStore` method takes the tenant, except `count_stale_vectors`, a platform-level count with no row content (a narrow `SECURITY DEFINER` function, migration `0007`). `CachePort` raises `CacheUnavailable` when the backend fails; callers choose to degrade (the response cache) or to deny (the limits, the web sessions).
- **The registry is the composition root.** `adapters/registry.py` builds one `Adapters` bundle (`ports/bundle.py`) from `Settings` in the `api/main.py` lifespan and puts it on `app.state.adapters`. Routes, the gateway (`GatewayRuntime(pool, cache, events)`), the agent and the MCP tools receive ports from it and never an SDK. Swapping a provider is a change to the registry and its settings (`LLM_MODEL`, `EMBED_MODEL`, `EMBED_FALLBACK_MODELS`, `OBJECT_STORE` and the `S3_*` values).
- **Tests use the same registry.** `build_adapters(settings, pool=..., overrides={...})` and `create_app(adapter_overrides=...)` put fakes (`tests/fakes.py`) behind any port. An unknown override name is refused, so a typo cannot keep a real adapter. Monkeypatching `litellm` remains only in the network-guard tests, the adapter unit tests and the contract suites that run the LiteLLM adapters.
- **Import-lint (tests/unit/test_import_lint_ports.py).**
  - `litellm`, `langchain_litellm`, `boto3` and `aioboto3`, and `redis`: only in `adapters/`.
  - `asyncpg`: only in `adapters/`, `core/database/` and `core/identity/store.py`. Routes and services that only need a type use `core.database.tenant.DbPool` and `DbRecord`.
  - The older rule stays: agent tools, the agent graph and the MCP code import no provider, no `asyncpg`, and load none with `importlib`.
  - **Not covered:** `scripts/labs/` holds historical lab scripts. They are outside the import lint and may import providers directly.
  - **Why identity stays:** `core/identity/store.py` authenticates a credential before any tenant is known, through `SECURITY DEFINER` functions. It is not a tenant-scoped store, so it is not a `KnowledgeStore`, and a port for it would add a layer with no second implementation. It stays where it is, behind the `Authenticator` seam.
  - **Not moved:** the usage, feedback, analytics, console and MCP ingestion-status queries still run through `tenant_connection(DbPool, tenant)` in their routers. They read `usage_log`, `feedback` and `gateway_decisions`, which are not knowledge data. They import no driver.
- **Contract tests (tests/contracts/).** One suite per port runs against every adapter: real and fake must pass the same file. The object store suite also runs against a live MinIO when the environment has one (`scripts/verify/minio.sh`).
- **Embedding provenance.** Every chunk records `embedding_model` and `embedding_dim` (migration `0007`, not null). Search, text and vector, only reads rows of the query's model and dimension. Rows of another model are stale: they are ignored, never matched wrongly, and counted in `/v1/health` as `stale_vectors`. The exact cache key and the semantic cache entries carry the embedding model too.
- **Embedding fallback.** `EMBED_FALLBACK_MODELS` is an ordered list. If the primary fails the next is tried. A provider whose vectors have another width than `EMBEDDING_DIM` is refused, logged at error level and skipped. If none works the call raises, so ingestion and search deny rather than store or compare wrong vectors. Rows made by a fallback say so in `embedding_model`.

## Consequences
- Swapping a provider is a config change, and tests use fake adapters.
- A re-embed can run alongside the old vectors, because vectors are versioned by model. The re-embedding job itself is not built; `stale_vectors` is its seam.
- The agent's best-effort cost call (`litellm.completion_cost` with token arguments) is moved as it was and still raises inside the adapter, which the graph swallows. Fixing it would change the reported agent cost, so it is left for a decision.
- Adds a thin layer of interfaces to maintain.

## Alternatives considered
- **LiteLLM strings everywhere (status quo):** they lock call sites to one library and make faking harder.
- **A heavy framework abstraction or a plugin system:** more surface than needed. One registry, built from settings.
- **Hiding the SQL of every table behind a port:** deferred; only the knowledge data moved.

# Architecture

For engineers who build on or change the platform. It describes the system as it is: its parts, how a request flows, and the rules every change keeps. The reasons behind each choice are in the [ADRs](adr/README.md).

## 1. Context

```
 people (console, workspace)        agents, scripts, MCP clients
            |  cookie session                  |  API key or JWT
            v                                  v
   +--------------------- the platform ----------------------+
   |  API (FastAPI, /v1)   workers   Postgres   Valkey         |
   +---------------------------------------------------------+
            |                    |                  |
   model providers        object store        event consumers
   (LiteLLM)              (local disk or S3)   (in-process or Kafka)
```

The platform is a modular monolith ([ADR-0001](adr/0001-modular-monolith.md)). The API and the workers run the same code and image, with different entry points. Postgres is the source of truth ([ADR-0002](adr/0002-postgres-source-of-truth.md)). Valkey holds caches, rate and budget counters and web sessions, all of which can be rebuilt.

## 2. Rules every change keeps
1. **Identity from a verified credential only.** Tenant and principal never come from a header, body or query.
2. **Every tenant-owned row has `tenant_id`, enforced by Postgres row-level security.** No code bypasses it.
3. **Fail closed.** If authentication, policy, budget, cost or guardrails cannot run, the answer is deny.
4. **Governance lives outside the agent.** Every model, tool and knowledge-base call goes through `gateway.enforce()`, inside the request's execution boundary.
5. **Authority only narrows.** A delegated agent or tool never gets more permission than its caller.
6. **Postgres is the source of truth.** Caches are derived. Raw files are never changed and are addressed by hash.
7. **Schema changes only through migrations,** versioned and forward only.
8. **Contracts first.** Typed Pydantic models, OpenAPI and `/v1` versioning.
9. **Open standards:** MCP, OAuth2 and JWT, OpenTelemetry, OpenAPI, CloudEvents.
10. **Everything is traceable.** Each request has a request id and a trace id, and each governed call has a decision record that holds hashes, never content.
11. **Every side effect is idempotent.** Writes and jobs carry idempotency keys and are safe to retry.
12. **Providers sit behind ports.** Swapping one is a configuration change. Vectors record the model and dimension that produced them.
13. **Stateless compute.** Any API or worker process can stop at any time. State lives in the stores.
14. **Configuration is validated at startup.** A wrong or missing value stops the process. Secrets never appear in code or logs.
15. **CI must pass:** lint, type checks, tests and the eval gate.

## 3. Building blocks

| Package | Responsibility |
|---|---|
| `api/` | The FastAPI app: middleware, `/v1` routes, the LangGraph agent (`api/agent/`), the MCP server (`api/mcp/`), the web edge session (`api/web_edge/`), the error format (`api/errors.py`) |
| `gateway/` | `enforce()` and its stages, the execution boundary, tenant policies, the reason catalogue, decision records, the hash chain and receipts |
| `core/` | Validated settings (`core/settings.py`), database pool and tenant connections, identity (keys, JWT, run tokens), ingestion, the job queue SQL, metrics |
| `ports/` | Typed interfaces to every external provider: LLM, chat model, embeddings, knowledge store, cache, object store, event bus, agent runtime, sandbox driver |
| `adapters/` | The implementations behind the ports, and `adapters/registry.py`, which builds one bundle from settings at startup. Only this package imports a provider SDK. |
| `workers/` | `python -m workers`: the job loop, the handlers (ingest, agent run, purge), the retention scheduler, the outbox relay and an optional metrics server |
| `sandbox_agent/` | The standard-library program that runs inside an OpenShell sandbox and reaches the platform only through the sandbox routes |
| `migrations/` | Alembic migrations `0001` to `0010` |
| `ui/` | The React and TypeScript console, workspace and public pages |

The port interfaces are listed in [contracts/ports.md](contracts/ports.md). Import-lint tests enforce the package boundaries: only `adapters/` imports `litellm`, `boto3`, `redis`, `aiokafka` or `openshell`, and agent code never imports the model client directly ([ADR-0005](adr/0005-ports-and-adapters.md)).

## 4. A request, step by step

1. **Middleware**, outermost first: metrics, CORS, request id, logging, latency, **auth**, FinOps.
2. **Auth** accepts a bearer API key, a JWT or a web session cookie, and puts a frozen `Principal` (id, tenant, kind, scopes) on the request. Without a valid credential the answer is `401`. Public paths are `/`, `/health`, `/v1/health` and the OpenAPI docs. Signing in (`POST /v1/session` and `/v1/session/preview`) needs no prior credential. `/metrics` is open only when `METRICS_PUBLIC` is true, and otherwise needs `admin`.
3. **The route** declares its scope and reads the tenant only from the principal.
4. **`gateway.enforce()`** runs for every model, tool and knowledge-base call. It is described in the next section.
5. **The work** runs through ports: retrieval in Postgres, completion through LiteLLM, cache in Valkey.
6. **The response** carries the request id. Errors use one format: `{"error": {"code", "message", "request_id"}}`.

## 5. The gateway

`enforce(ctx, action)` runs these stages in order, and the first deny wins ([ADR-0004](adr/0004-governance-outside-the-agent.md), [ADR-0006](adr/0006-gateway-enforce-pipeline.md)):

| Stage | Checks |
|---|---|
| `principal` | The caller exists, is not disabled, and has a scope that grants the action |
| `boundary` | The action fits the execution boundary: the knowledge bases, tools and models the request may use, and its tool-call count |
| `policy` | The tenant's active policy allows it: knowledge bases, tools, models, limits and tool argument schemas |
| `guardrails` | Input length and blocked terms |
| `rate` | The per-principal rate limit (Valkey) |
| `budget` | The tenant's daily token budget (Valkey) |
| `cost` | The tenant's daily cost cap in USD (Valkey) |

Any exception inside a stage is a deny. An action has a kind (`kb.read`, `kb.write`, `model.invoke`, `tool.call`, `agent.run`, `feedback.write`, `analytics.read` or `audit.read`), a resource and the SHA-256 of its input. Every reason a stage can give is in the reason catalogue (`gateway/reasons.py`), with a plain sentence and the policy field it points to. The table is in [api/README.md](api/README.md#reason-codes).

**The execution boundary** is created once per request from the principal and the policy. It is passed to the agent and to MCP in the run configuration, never as an argument the model could set. A delegated boundary is always a subset of its parent.

**Policies** are versioned documents per tenant. Publishing one creates a new version, and the newest is active from the next request. A tenant without a policy gets the platform default: what the key's scopes grant. A list left out of a policy allows nothing. A `tool_arguments` entry holds a JSON Schema per tool. Schemas may not use regular expressions, and a check that takes longer than 0.25 seconds is a deny.

## 6. Decision records, the hash chain and receipts

Every `enforce()` call writes one row to `gateway_decisions`: the action, resource, outcome, stage, reason, policy version, request id, `execution_id` of the run that caused it, and the SHA-256 of the input. Input text is never stored.

- **Fail closed.** If the row cannot be written on an allow, the call answers `503 decision_unrecorded` and nothing runs. A deny keeps its row.
- **Hash chain.** Rows are chained per tenant under an advisory lock: `row_hash = sha256(canonical_json(record) || prev_hash)`. Editing, removing or reordering a row breaks the chain.
- **Receipts.** `GET /v1/receipts/{decision_id}` returns the record, its chain position and an Ed25519 signature over the canonical JSON. `scripts/verify/receipt.py` verifies a receipt offline with the public key, and `POST /v1/receipts/verify` does the same checks on the server. Old public keys stay listed after a key rotation ([ADR-0012](adr/0012-receipts-and-hash-chain.md)).
- **Retention.** Records are kept for `DECISION_RETENTION_DAYS` (90 by default), and a tenant can set its own value. The floor is 30 days. A daily purge job deletes expired rows of one tenant in batches. It writes a signed checkpoint first, so the chain still verifies after the purge.

## 7. Tenancy and data

- **Identity tables:** `tenants`, `principals` (user, service or agent), `api_keys` (prefix and a hash of the secret, scopes, revoked time), `knowledge_bases` (per tenant), and `run_tokens` for sandboxed runs.
- **Tenant-owned tables** have `tenant_id` and forced row-level security with the policy `tenant_id = current_setting('app.tenant_id')`. A missing setting means zero rows. Every query runs in `tenant_connection(tenant_id)`.
- **Roles.** The app connects as `gap_app`, which is neither superuser nor `BYPASSRLS`. The API refuses to start otherwise. The owner role runs migrations and the admin CLI. The few lookups that must run before a tenant is known (key, principal, preview principal, run token) are narrow `SECURITY DEFINER` functions with a fixed `search_path`.
- **Documents** are stored as chunks with their embedding, text, metadata, `embedding_model` and `embedding_dim`. Search reads only chunks of the active model. Others are counted as `stale_vectors` in `/v1/health`.
- **Raw files** are stored once in the object store under their SHA-256.

The data model is defined by the migrations in `migrations/versions/` ([ADR-0003](adr/0003-tenancy-row-level-security.md)).

## 8. Retrieval and the agent

- **Search** is hybrid: keyword search (Postgres full-text `ts_rank`) and pgvector similarity, merged with reciprocal rank fusion. An optional cross-encoder reranker runs where the image includes it. The names `bm25_only` and `bm25_score` remain compatibility values; this ranking is not true BM25. Answers carry citations and a confidence level, and a low score refuses to answer.
- **Caches:** an exact-match cache and a semantic cache in Valkey, keyed by tenant and embedding model.
- **The agent** is a LangGraph graph with a retrieve tool and a verify loop. Every model and tool call goes through the gateway, with the run's boundary.
- **MCP:** the same tools and resources are served over MCP (`/v1/mcp/sse`, `/v1/mcp/messages`), with the same credential and the same gateway.

## 9. Jobs, workers and agent runs

- **Queue.** Jobs live in the `jobs` table. Workers claim them with `FOR UPDATE SKIP LOCKED`, hold a lease, retry with backoff and mark a job `dead` after its last attempt. An idempotency key is unique per tenant. A job whose worker dies is claimed again after its lease ends ([ADR-0011](adr/0011-durable-jobs.md)).
- **Kinds:** `ingest`, `agent_run` and `purge_decisions`.
- **Ingestion.** `POST /v1/ingest` stores the raw bytes and answers `202` with a job. The worker chunks, embeds and reports progress per batch.
- **Agent runs.** `POST /v1/agent/query` queues a run with a new `execution_id`. It waits up to `AGENT_SYNC_WAIT_SECONDS` and answers with the result, or `202` with the execution id. Usage is booked once per `execution_id`.
- **Runtimes** sit behind the `AgentRuntime` port ([ADR-0009](adr/0009-agent-runtime.md)): `queued` (the default, a job), `inprocess` (in the API process), and `openshell` (in a sandbox).
- **Visibility.** Job and run routes show only knowledge bases the caller's boundary allows. Without `audit:read`, a caller sees only its own runs.

## 10. Sandboxed runs

With `AGENT_RUNTIME=openshell`, the worker runs each agent run inside an OpenShell sandbox:
- The sandbox's only network route is the platform's sandbox routes. Direct calls to model providers are refused.
- Its only writable place is one work directory. CPU, memory and wall time are limited.
- It gets a run token: a short-lived credential bound to one `execution_id`, valid only on `/v1/sandbox/runs/{execution_id}/...`, with the boundary frozen at creation. Only a hash is stored. It ends with the run, or when the key that started the run is revoked.
- Tool arguments are checked against the policy's schemas before a tool runs.
- Sandbox events (start, exit, network denied, file denied, limit hit) are stored in `sandbox_events` and merged with the decisions on the run timeline.

What the agent reports itself (citations, usage, confidence) is marked `agent_reported`. Usage is booked from what the gateway measured. Setting up OpenShell is in [operations.md](operations.md#sandboxed-runs-openshell).

## 11. Events

Events are CloudEvents 1.0 ([ADR-0008](adr/0008-event-bus.md)). The types and their data are in [contracts/README.md](contracts/README.md).
- **Outbox.** An event is written to the `outbox` table in the same transaction as the change that caused it, so it is never lost and never sent for a change that rolled back.
- **Relay.** A worker relays outbox rows to the bus at least once. A tenant's events go out in order.
- **Bus.** `EVENT_BUS=outbox` (the default) delivers to in-process subscribers. `EVENT_BUS=kafka` publishes to Kafka topics `platform.<type>`, keyed by tenant id, in binary mode. Kafka is never reached inside a request.
- **Consumers** dedupe by CloudEvent id in `processed_events`. A Kafka message that keeps failing goes to `<topic>.dlq`.

## 12. The web edge and the UI

- **Sessions.** The browser never holds an API key. `POST /v1/session` takes a key once and sets the `gap_session` cookie (HttpOnly, SameSite=Strict). Writes need a CSRF header. Revoking the key ends the session. An optional read-only preview session can be enabled for one principal ([ADR-0007](adr/0007-web-edge-session.md)).
- **UI.** React with TypeScript, Tailwind and Radix components, TanStack Query and a client typed from the OpenAPI spec. The design system is in [design/](design/README.md).

## 13. Cross-cutting concerns

- **Configuration:** one validated `Settings` object ([configuration.md](configuration.md)).
- **Errors:** one format, and deny reasons map to stable codes ([api/README.md](api/README.md#errors)).
- **Logs:** JSON lines with the request id, trace id, tenant and principal. Input text and secrets are not logged.
- **Tracing:** OpenTelemetry spans for FastAPI.
- **Metrics:** Prometheus format at `/metrics` ([operations.md](operations.md#metrics)).
- **Evaluation:** a fixed suite runs in CI with test models and fails on a regression against `scripts/eval/baseline.json`.

## 14. Key decisions

| Decision | ADR |
|---|---|
| A modular monolith | [0001](adr/0001-modular-monolith.md) |
| Postgres as the source of truth | [0002](adr/0002-postgres-source-of-truth.md) |
| Tenancy with row-level security | [0003](adr/0003-tenancy-row-level-security.md) |
| Governance outside the agent | [0004](adr/0004-governance-outside-the-agent.md) |
| Ports and adapters | [0005](adr/0005-ports-and-adapters.md) |
| The `enforce()` pipeline | [0006](adr/0006-gateway-enforce-pipeline.md) |
| The web edge session | [0007](adr/0007-web-edge-session.md) |
| The event bus and CloudEvents | [0008](adr/0008-event-bus.md) |
| The agent runtime and sandbox | [0009](adr/0009-agent-runtime.md) |
| Design tokens and the palette | [0010](adr/0010-design-tokens-and-ink-paper-palette.md) |
| Durable jobs on Postgres | [0011](adr/0011-durable-jobs.md) |
| Receipts and the hash chain | [0012](adr/0012-receipts-and-hash-chain.md) |

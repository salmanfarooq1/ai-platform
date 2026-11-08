# Vision and target architecture

## The idea in one line
Proof from source row to agent answer: every answer can be traced back to the data it read, the policy that allowed it, and a signed receipt anyone can verify offline.

## Why this is different (research, Oct 2026)
- Big vendors (Databricks Unity AI Gateway, Snowflake Horizon, AWS AgentCore, Google Agent Gateway, Microsoft Entra Agent ID) each own one piece. All of them sell logs, not proofs.
- Nobody joins data lineage, agent actions and policy decisions in one verifiable chain.
- Open gaps we fill:
  - agent facets for OpenLineage
  - data contracts (ODCS 3.2 agent context) compiled into runtime policy
  - purpose binding from grant to query
  - approvals bound to the exact action
  - governed agent memory
  - SCITT-shaped receipts with offline replay of "why was this allowed"
  - evidence packs mapped to the EU AI Act
  - dashboards and reports where every number has a receipt, read under the viewer's own grants
- Table stakes by 2027 (we need them, they do not set us apart): MCP and A2A support, OTel GenAI traces, OIDC for agents, PII guardrails, budgets, a sandboxed runtime, audit logs.
- The Digital Omnibus on AI is law: Regulation (EU) 2026/1744, published in the Official Journal on 24 July 2026. Annex III applies from 2 December 2027 and Annex I from 2 August 2028. Article 50 applies from 2 August 2026. Sprint 019 includes its content-disclosure requirement. [Official text](https://eur-lex.europa.eu/eli/reg/2026/1744/oj).

## Three pillars and integration first (owner direction, 2026-10-11)
| Pillar | What it covers | Modules |
|---|---|---|
| **Gateway** (security) | Identity, policy, guardrails, approvals, evidence and receipts, and the protocol front (MCP, OpenAI-style LLM API, A2A). It governs every call and is mature as a product on its own. | M1, M2 |
| **Data** | Connections to client sources, warehouses and streams, the lakehouse, pipelines, contracts, quality, grants, lineage, the semantic layer, retrieval, grounding, memory data and BI. Better data structure gives better retrieval. | M4, M5, M6 |
| **Agents** | Execution and sandboxes, our agents and templates, client and external agents, monitoring, memory and autonomy. | M3 |

**Integration first.**
- Clients connect what they already have: agents, data sources, event streams and warehouses.
- We use existing open-source connectors (dlt, Debezium, DuckDB extensions, Trino, MCP servers) and govern them. We do not rebuild the client's stack.
- Integration agents inspect a new connection, read the schemas on both sides, and suggest mappings and issues. A human approves.

**One way to govern every agent.** Our agents, the client's agents and external agents (Copilot, Claude Desktop, Cursor, LangChain apps) are treated the same:
- Every call goes through the gateway with a standard request contract: bearer token (`aud`, `iss`, `exp`, `sub`, optional `act`), agent id, `traceparent`, run id and purpose.
- The deployment closes every other route:
  - Our agents run in the sandbox.
  - Client agents run under default-deny egress.
  - External agents reach tools and data only through endpoints we own.

**Gateway deployment modes** (016):
| Mode | When | How |
|---|---|---|
| Embedded | Our own agents and services, in process | `enforce()` as today |
| Sidecar | Client agents in their cluster | The `authorize()` service next to the agent |
| Standalone proxy | External agents, shared tools, LLM traffic | A proxy for MCP, the OpenAI-style API and A2A. Our engine is the only decision maker and record writer in every mode. The optional agentgateway data-plane spike is in 028. |

**Data access adapters** (021). All of them sit behind `DataAccess`, take the same compiled grant and return the same receipt fields:
| Adapter | Engine | Use |
|---|---|---|
| Direct | DuckDB ATTACH, read-only, locked | Client Postgres, MySQL, SQLite, files and Excel, read in place |
| Federated | Trino with the OPA plugin | Many sources and joins. Trino enforces filters and masks as a second layer. |
| Lakehouse | DuckLake | Data we must hold: pipeline output, documents, extracted tables |
| Native (optional) | The warehouse's own engine under a narrow read-only role | Snowflake, BigQuery or Databricks, when the client wants their native policies too |

The gateway always rewrites the SQL first. Engine or native policies are defence in depth, never the only control.

**Deployment shape.**
- Single-tenant per deploy is the default. Each client gets its own install, and RLS stays as defence in depth.
- Multi-tenant is supported for a hosted offering.
- Local Compose is the development and proof-of-concept vehicle. Real deployments run on cloud with one OpenTofu module per cloud (031) and the same core.

## Modules, editions and cross-module ports
The code today is layered (`core/`, `gateway/`, `api/`, `workers/`), not split by module. Sprint 012 draws the boundaries before the data plane adds a lot of code.

| Module | Responsibility | Package (from 012) |
|---|---|---|
| **Kernel** (platform) | Postgres, Valkey, object store, event bus, workers, identity, telemetry, model access, settings | `core/`, `adapters/`, `ports/`, `workers/` |
| **M1 Gateway** | `enforce()`, policy, guardrails, approvals, protocol front | `gateway/` |
| **Evidence core** (ships with M1) | decision records, hash chain, current receipts | `evidence/` (split out of `gateway/` in 012) |
| **M2 Evidence** (upgrade) | COSE receipts and external anchoring (017), evidence packs and mappings (030), local transparency log and timestamp authority (031) | `evidence/` extensions |
| **M3 Agent Runtime** | agents, sandboxes, MCP server, memory | `api/agent/`, `sandbox_agent/`, `runtime/` |
| **M4 Data Plane** | lakehouse, pipelines, products, quality, grants, semantic layer | `dataplane/` (new in 021) |
| **M5 Lineage** | lineage store and graph | `lineage/` (new in 025) |
| **M6 Insights** | metric catalog, explore, dashboards, reports, alerts (business intelligence) | `insights/` (new in 029) |

The gateway cannot ship without the evidence core: `enforce()` fails closed when the decision write fails. So the evidence core is part of the gateway product. M2 sells the upgrade.

### Cross-module ports
| Port | Used by | Real adapter | No-op adapter (module off) |
|---|---|---|---|
| `DecisionSink` | M1 | Evidence core | none: the gateway always has it |
| `EvidenceLookup` | M5, UI | Evidence core, always on | contract fixture only; unknown/foreign ids return "not linked" |
| `DataAccess` | M3, M6 | M4 query path | denies with `module_disabled` |
| `LineageEmitter` | M3, M4, M6 | M5 store | 012 drops/counts before producers; 022 adds durable spool, consumed in 025 |
| `LineageLookup` | M4, M6 | M5 store (025) | returns "not linked" |
| `QueryEngine` | M4 | DuckDB | — (internal to M4) |
| `PolicyEngine` | M1 | Python engine (018), OPA (030) | — |

`DataAccess` grows by sprint (methods listed in `conventions.md`). `ReportDelivery` (029) is a provider port inside M6, not a cross-module port. The inbox is part of the kernel.

Rules: modules import only the kernel and `ports/`. Import-linter contracts in CI enforce this from Sprint 012. The gateway package API is the explicit public exception; its internals remain private. `ENABLED_MODULES` selects modules. Disabled modules hide their navigation group and return `module_disabled` on their routes.

### Editions (functional labels)
| Edition | Modules |
|---|---|
| Gateway | Kernel + M1 (with evidence core) |
| Assurance | Gateway + M2 |
| Agents | Gateway + M3 |
| Data | Gateway + M4 + M5 + M6 |
| Full | everything |

A CI matrix boots each edition and runs its smoke tests every sprint from 012.

## Target request path (ask-your-data)
1. A user asks a question. The tenant comes from the credential.
2. The gateway admits the run: principal, boundary, policy, declared purpose.
3. The agent runs in an OpenShell sandbox (mandatory for data agents). It has a run token and a run identity.
4. The agent picks a metric. MetricFlow compiles it to SQL. Filters are typed parameters.
5. The SQL is parsed. The guard allows one SELECT, allowed functions only, and only tables the caller has a grant for.
6. The rewrite step replaces each table with the grant's filtered and masked relation. A minimum group size applies to aggregates.
7. The `DataAccess` adapter runs it: DuckDB on a client source read in place, DuckLake, or Trino. It uses a locked connection and pins a snapshot or time-travel id wherever the source has one.
8. Output passes guardrails. Links and images are stripped. A tainted session loses tools that can send data out.
9. The model writes the answer through `model.invoke` (a local model by default).
10. The receipt names the SQL hash, metric ids, snapshot id, result hash, withheld columns, policy package hash and model digest. The chain head is externally anchored (017) and timestamped (031). A lineage event links source, pipeline, snapshot, run and answer.

## Lakehouse design (from the security and data reviews)
- **One DuckLake catalog per tenant** (multi-tenant deploys; a single-tenant deploy has one). Each tenant has its own metadata schema in the `lakehouse` database, its own data path prefix, and its own SeaweedFS identity limited to that prefix. A connection attaches only the caller's tenant catalog.
- **Locked connections.** After setup: `enable_external_access=false`, allowed paths only, no extension auto-install or auto-load, unsigned extensions refused, `memory_limit`, `threads` and a timeout set, then `lock_configuration=true`. Extensions are installed in the image, never fetched at runtime.
- **Secrets stay out of agents.** The catalog and S3 secrets never enter the agent, the sandbox or the model context.
- **Process model.** Reads run in a thread pool on per-request cursors from a bounded tenant-keyed connection cache. Agent and large queries run in a query worker. Writes run only in workers.
- **Single writer per table.** DuckLake uses optimistic concurrency, and some conflicts abort. Every write (upload, dbt, CDC sink, compaction) takes an advisory lock on the dataset id and retries on conflict.
- **Snapshots and retention.** Snapshots named in receipts are protected from expiry for the replay window. A maintenance job runs `checkpoint` work (flush inlined data, merge files, expire snapshots, clean up files). An erasure flow deletes rows, forces expiry and cleanup, and records which receipts can no longer be replayed.
- **Grants are enforced by rewriting SQL, not by views.** DuckDB views are not a security boundary. The query path parses the SQL and swaps each table for the grant's filtered and masked subquery. Only rewritten references are allowed.
- **Platform tables keep Postgres RLS.** Datasets, products, grants and lineage carry `tenant_id` as today.
- **Written exception to strict rule 7.** DuckLake manages its own catalog tables in the `lakehouse` database. Platform tables still change only through Alembic. ADR-0015 records this.

## Insights design (business intelligence)
People need numbers without asking an agent: metric catalogs, dashboards, scheduled reports and alerts. M6 Insights gives them that, on the same governed path the agent uses.
- **One metric path.** Tiles, reports and the agent all call the semantic layer (025) through `DataAccess`. So a metric means the same thing everywhere, and the gateway sees every read.
- **Viewer rights, never author rights.** A shared dashboard runs each tile under the viewer's grants and the dashboard's declared purpose. A report renders once per recipient, under that recipient's grants, and records who scheduled it (`on_behalf`).
- **Every number has a receipt.** Each tile is a `data.read` decision, even on a cache hit. One view pins one snapshot id, so numbers agree and can be replayed.
- **Certified metrics.** A metric is certified only when its source products are certified and a steward approved its definition hash.
- **Dashboards as code.** A dashboard is a versioned JSON document. It can be exported, reviewed and imported. No raw SQL or chart code.
- **Why not an external BI server.** Superset, Metabase, Lightdash and similar tools connect to the warehouse with their own service account. That bypasses the gateway, the grants and the receipts (design rule 1). A governed SQL endpoint that would let such tools read through the gateway gets a spike in 029.

## Design rules added by this program
These extend the 15 strict rules. Each is confirmed in the ADR named.
1. **The gateway is the only door to data.** Every read is a `data.read` action through `enforce()`. (ADR-0015)
2. **Every read pins a snapshot**, and the snapshot id is in the decision record. (ADR-0015)
3. **Contracts are executable.** An ODCS contract drives quality checks, masking and agent "must never" rules. No valid contract, no certification. (ADR-0018)
4. **Approval is not access.** An approved request becomes a grant through a queue. A grant has a purpose and an expiry. Requester and approver are different people. (ADR-0019)
5. **Lineage is evidence.** Lineage events carry decision ids, so lineage and the chain join. SQL literals are never stored, only hashes. (ADR-0020)
6. **Open by default, the client's choice of model and cloud.** The default stack uses only OSI licences, checked in CI. Hosted models (013), managed cloud services (031) and external anchors (017) are adapters the client chooses. One external anchor is on by default for client installs. (ADR-0014, revised)
7. **Decision records are versioned.** From 012, every record has a `record_version` and a canonical form, so later sprints add fields without changing the chain rules. (ADR-0013)
8. **A threat model per sprint.** Every pack has `threat-model.md`. QA signs it off.
9. **Standard discovery paths are the one exception to `/v1`.** Read-only, public discovery documents that a standard requires may live under `/.well-known/`: OAuth protected resource metadata (RFC 9728, 016), AuthZEN discovery (018) and the A2A Agent Card (028). They hold no tenant data and need no credential. Everything else stays under `/v1`. The first sprint that adds one (016) records this in `DECISIONS.md` and in `docs/architecture.md`.
10. **People and agents read through the same governed metric path.** Dashboards, reports and alerts render under the reader's own grants, never with the author's or a service identity. (ADR-0031)
11. **No route around the gateway.** Every agent, ours or not, reaches tools, models and data only through the gateway. Each deployment mode states how other routes are closed, and a canary test proves it. (ADR-0023, revised)
12. **Integrate before we ingest.** Read client data in place when we can. Copy into the lakehouse only what must be held, and say why in the pipeline definition. (ADR-0015, revised)

## Planned ADRs
| ADR | Title | Sprint |
|---|---|---|
| 0013 | Module boundaries, cross-module ports and decision record v2 | 012 |
| 0014 | Model choice (local or hosted), the provider register and the licence gate | 013 |
| 0015 | Data access adapters (direct, federated, lakehouse), locked connections, gateway-only access | 021 |
| 0016 | Pipelines on the job queue, dbt as the transform layer | 022 |
| 0017 | Change data capture with Debezium, Kafka and our own sink | 022 |
| 0018 | Data products and contracts, and the product lifecycle | 023 |
| 0019 | Access grants, purpose and query rewriting | 024 |
| 0020 | Lineage model and agent facets | 025 |
| 0021 | Semantic layer first, parsed and guarded SQL second | 025 |
| 0022 | Versioned policy package, three outcomes, replayable decisions | 018 |
| 0023 | Gateway service, deployment modes, MCP 2026-07-28 front and upstream proxy | 016 |
| 0024 | Human approvals bound to the action hash | 019 |
| 0025 | External identity provider and delegation | 020 |
| 0026 | A2A v1.0 and signed Agent Cards | 028 |
| 0027 | Guardrail models | 019 |
| 0028 | Governed agent memory and autonomy tiers | 028 |
| 0029 | Receipts v2: COSE, SCITT shape, key management | 017 |
| 0030 | External receipt anchoring | 017 |
| 0031 | Governed business intelligence on the semantic layer | 029 |
| 0032 | Local POC lifecycle, Compose bundle and backups | 015 |
| 0033 | Documents, retrieval and grounding | 026 |
| 0034 | Resilience, encryption at rest, keys, local transparency log and timestamping | 031 |

# Sprint map: 011 to 032

Milestones, not dates. A sprint is done when its acceptance checks pass and QA signs off. Feature sprints are vertical slices: the contract first (OpenAPI under `/v1`), then backend, then UI, then at least one e2e test across both.

**History.** The first draft had 20 sprints. The six reviews split it into 34, and the owner review (BI) made it 36. On 2026-10-11 the owner set a new direction ([Program 2 direction in `DECISIONS.md`](../DECISIONS.md)), and a five-direction review added scope (`review.md`). The map is now **22 sprints**:
- The direction is integration first, three pillars, and a cloud deployment path.
- The new scope from the review: the gateway as a proxy, federation over client data, retrieval and grounding, cloud lifecycle, and enterprise gaps.
- Each sprint is larger than 009 or 010. It may take two Builder runs (part a, part b), but it stays one pack, one QA sign-off and one tag.
- The old 36 packs are kept in `planning/sprints/_draft-36/` as source material. The table at the end maps old to new.

## The three pillars
| Pillar | What it covers | Modules |
|---|---|---|
| **Gateway** (security) | Identity, policy, guardrails, approvals, evidence and receipts, the protocol front (MCP, LLM API, A2A). Mature as a product on its own. | M1, M2 |
| **Data** | Connections to client sources and warehouses, lakehouse, pipelines, contracts, quality, grants, lineage, semantic layer, retrieval, grounding, BI. | M4, M5, M6 |
| **Agents** | Execution, sandboxes, our agents and templates, client and external agents, monitoring, memory. | M3 |

The Kernel (platform) sits under all three. **Integration first** holds in every pillar. Clients connect their own agents, sources, streams and warehouses through existing connectors, and all of them are governed the same way through the gateway.

## Milestones
| Milestone | Sprints | Showcase journey (script + Playwright e2e on the reference company) | Tag |
|---|---|---|---|
| **M0 Foundations** | 011–015 | `poc up` brings the stack up on a cloud VM from one command. A model call (local or hosted) is denied by policy, and the receipt names the model. Modules can be switched off. `poc backup` and `poc down` leave nothing running, and `poc up` restores it. | `v0.15.0` |
| **MG Gateway product** | 016–020 | An external MCP client and an OpenAI-style client call through the standalone proxy. A tool call needs a human approval. A PII prompt is masked. An SSO user acts through a delegated run identity. Every decision has a COSE receipt anchored outside the host, and "why was this allowed" replays offline. | `v0.20.0` |
| **MD Data on the client's stack** | 021–026 | A client Postgres and a CSV folder are connected in place, with no copy. A steward certifies a product with a contract. An analyst requests access with a purpose and reads masked rows. Lineage shows every step. A policy document question is answered with span citations, or the system abstains. | `v0.26.0` |
| **MA Agents and insights** | 027–029 | "What was Q3 gross margin by region?" is answered in a sandbox, with metric, snapshot and masked columns in the receipt. An integration agent maps a newly connected CRM schema, and a human approves it. A runaway agent is stopped by its budget breaker. A finance dashboard shows different numbers to two viewers, and every tile has a receipt. | `v0.29.0` |
| **ME Enterprise readiness** | 030–032 | An auditor exports a signed evidence pack and verifies it offline. Decisions stream to a SIEM. A failover drill meets the stated RPO and RTO targets on a second cloud. Each edition installs on its own and passes its smoke tests. | `v1.0.0` |

**Sellable point.** After 020 (`v0.20.0`), the Gateway and Assurance editions stand on their own. They govern our agents and the client's existing agents and tools, with signed receipts. This is the earliest product for security POCs.

**Freeze point.** If time runs out, the tag after 027 (`v0.27.0`) is a complete first version. It gives the full chain from a client source row, read in place, to a signed agent answer.

## Sprint list
| # | Slug | Pillar | Goal | From old | Depends on | ADR |
|---|---|---|---|---|---|---|
| 011 | `baseline-and-stack` | Platform | Planning drift fixed, exact pins and the licence gate (LiteLLM licence and supply-chain check included), SBOM, secret scan, threat-model template. Valkey, Apache Kafka (optional profile) and SeaweedFS replace non-OSI parts. Docker Engine documented, ports bound to localhost, compose healthchecks and profiles. The keyword search leg is named for what it is (`ts_rank`, not BM25). | 011, 012 | — | — |
| 012 | `pillars-and-boundaries` | all | Evidence core split out of the gateway. Modules mapped to the three pillars. Cross-module ports with no-op adapters, import-linter contracts, `ENABLED_MODULES`, module registry, edition smoke matrix. Decision record v2. Single-tenant per deploy is the default deploy shape, and RLS stays as defence in depth. Information architecture. | 013 | 011 | ADR-0013 |
| 013 | `models-and-providers` | Gateway | Local models pinned (`models.lock`, digests). Hosted providers (Azure OpenAI, Bedrock, Anthropic, OpenAI-compatible vLLM) are an equal option through the existing LiteLLM adapter. A per-provider data-use and residency register, a region pin in policy, and the model digest or provider id in records. CPU, GPU and hosted profiles. | 014 + new | 012 | ADR-0014 (revised) |
| 014 | `reference-company` | Platform | A fictional distributor: finance, CRM, HR and document generators, a source Postgres with a change generator, personas with keys, and the showcase script skeleton. Generators can emit a client-shaped variant from a schema file. | 015 | 013 | — |
| 015 | `cloud-poc-lifecycle` | Platform | OpenTofu interface contract and the first cloud VM module. Compose bundle with images pinned by GHCR digest and a wheelhouse. `poc up/seed/demo/backup/down` with a restore test. An upgrade-from-previous-release CI job. Idle cost recorded. | new | 014 | ADR-0032 |
| 016 | `gateway-service-and-proxy` | Gateway | A stateless `authorize()` service over `enforce()` (AuthZEN-shaped input), and the request contract every agent call must carry. Agent registry v1 with a stopped flag (the kill switch). MCP 2026-07-28 front: protected resource metadata, audience binding, no token passthrough, pinned tool definitions, private registry. OpenAI-compatible LLM route. agentgateway spike with a fail-closed test. Egress templates and a canary test. | 033 + new | 015 | ADR-0023 (revised) |
| 017 | `receipts-v2-and-anchoring` | Gateway | COSE_Sign1 receipts with `kid` in SCITT shape. Separate keys behind a signing-key port (file, PKCS#11, cloud KMS). Rotation and revocation drill. Local transparency log and timestamp authority. One external anchor on by default for client installs. Standalone verifier package with test vectors. | 040, 041 | 016 | ADR-0029, ADR-0030 |
| 018 | `policy-engine-and-replay` | Gateway | OPA adapter on the `PolicyEngine` seam, one decision-table suite for both engines, three outcomes, the purpose stage and purpose in policy. Policy bundle and input hashes for replay. AuthZEN 1.0 API with interop tests. Policy test bench, what-if over recorded inputs, replay of "why was this allowed". First tenant policies. | 031, 032 | 017 | ADR-0022 |
| 019 | `guardrails-and-approvals` | Gateway | Presidio on input and output, a local guard model with its digest in records, and a guard-provider port for third-party engines. The one approval model: bound to the canonical action hash, single use, re-checked at execution, separation of duties. Inbox, MCP elicitation, stop and override route, oversight log. Approval webhook for Jira or ServiceNow. | 038, 034 | 018 | ADR-0024, ADR-0027 |
| 020 | `identity-and-access` | Gateway | Keycloak 26.8.x SSO for the console, SCIM 2.0 provisioning, enforced MFA, custom roles, a read-only auditor role, session policy, IP allowlist at the proxy and app, service clients. Platform-minted delegation tokens (`act`, `may_act`, audience limits, narrowing only), SPIFFE-format run ids, delegation chain in records. | 035, 036 | 019 | ADR-0025 |
| 021 | `data-access-and-federation` | Data | `DataAccess` adapters: Direct (DuckDB ATTACH, read-only, locked), Lakehouse (DuckLake) and a Federated spike (Trino with the OPA plugin). Connection registry with credentials from the secret store. `data.read` action, snapshot or time-travel id in records, SQL parse base (sqlglot). | 016 + new | 020 | ADR-0015 (revised) |
| 022 | `connectors-pipelines-transforms` | Data | dlt sources (files and Excel, SQL databases, HTTP behind an egress allowlist, SaaS APIs). Lakehouse write path: single writer, protected snapshots, retention, erasure, backups. Pipelines on the job queue with run history and backfill. dbt on DuckLake from generated projects. Client event streams through Kafka Connect or Debezium Server (optional profile). | 017, 018, 019, 020 | 021 | ADR-0016, ADR-0017 |
| 023 | `products-contracts-quality` | Data | Data products (ODPS 1.1) and contracts (ODCS 3.2), versions and breaking-change diff, lifecycle, classification, glossary, catalog search. Contract "must never" rules compiled into policy data. Catalog import from OpenMetadata or DataHub. Auto-checks, certification, quality score, freshness SLOs. | 021, 022 + 032 part | 022 | ADR-0018 |
| 024 | `grants-and-query-enforcement` | Data + Gateway | Listings, access requests with purpose (on the 019 approval model), grants, expiry, revocation. Grants enforced by rewriting SQL (row filters, column masks), minimum group size, cache keys with grant version, bypass corpus. Trino or native warehouse policies pushed as defence in depth. | 023, 024 | 023 | ADR-0019 |
| 025 | `lineage-and-semantic-layer` | Data | Lineage store, OpenLineage from pipelines, dbt and streams, OpenMetadata lineage import, agent facets, decision ids through `EvidenceLookup`. MetricFlow compile, then rewrite, then guard. Parsed SQL guard with a function allowlist, typed filters, injection fuzz corpus. | 025, 026 | 024 | ADR-0020, ADR-0021 |
| 026 | `documents-retrieval-grounding` | Data | Docling offline: structure-aware chunks and extraction into contract-shaped tables with a review queue. True BM25 (`pg_textsearch`) beside pgvector. Per-chunk ACLs and an `AclFilter`. Grounding gate: sufficiency check, span citations, NLI check, abstention. Labelled eval set (RAGAS, TruLens). `ExternalIndex` adapter for a client's pgvector. Malicious-PDF test. | 030 + new | 025 | ADR-0033 |
| 027 | `data-and-integration-agents` | Agents | Agent tools on `DataAccess`, sandbox mandatory, session taint and the lethal-trifecta breaker, output link stripping, answer receipts, Ask-data UI, result-set evals, nightly red team. Integration agents: inspect a new connection, read both schemas, suggest mappings and issues (Valentine/bdikit plus the model). A human approves, and everything goes through the gateway. | 027 + new | 026 | — |
| 028 | `agent-registry-monitoring-memory` | Agents | A2A v1.0 with signed Agent Cards. One registry for our, client and external agents, with agent templates and bring-your-own registration. OTel GenAI spans with `decision_id`, the collector, loop and budget breakers, stop-run, anomaly alerts. Governed memory with a token budget and summarise-on-overflow, autonomy tiers, incident log. | 037, 039, 044 part | 027 | ADR-0026, ADR-0028 |
| 029 | `insights` | Data | Metric catalog, dashboards as versioned documents read under the viewer's grants with one snapshot per view, a receipt per tile. Reports per recipient (PDF, CSV, inbox, optional SMTP), metric alerts. Governed SQL endpoint spike for external BI tools. | 028, 029 | 028 | ADR-0031 |
| 030 | `evidence-packs-and-siem` | Gateway | Signed evidence packs per system and window, retention floor for high-risk systems, audit search. System card, model cards, ML-BOM, impact assessment templates, EU AI Act, ISO 42001, NIST and OWASP mappings backed by tests. SIEM export (OCSF; Splunk HEC first). Chargeback and showback by cost centre. | 042, 043, 044 part | 029 | — |
| 031 | `resilience-and-cloud` | Platform | Stated RPO and RTO targets and a failover drill. HA reference: managed Postgres or Patroni, app replicas, worker failover. Encryption at rest (managed or volume) and a data-key KMS port. OpenBao secrets with External Secrets Operator. Second and third cloud modules and one Helm chart. | new | 030 | ADR-0034 |
| 032 | `release-and-trust` | Platform | Per-edition packages and installs, release SBOM and signing, air-gap bundle. WCAG 2.2 AA checks and an ACR. CAIQ v4 answers, pen test (Strix, ZAP), `security.txt` and a disclosure policy. Exit and portability runbook. One scripted walkthrough of every milestone, plus a final docs pass. | 045, 046 + new | 031 | — |

## Tracks outside the sprint map
- **POC kit.** It is planned with the owner first, because the client data shape is unknown ([DECISIONS.md](../DECISIONS.md), Program 2 direction). The earliest it can start is after 015 (`poc` lifecycle) and 021 (connect in place).
- **Portfolio.** 2–3 public projects in their own repos. They use a different domain and a fresh small core, with no private code. They are not part of this map.

## Order notes
- **Gateway first.** The security pillar is the clearest product and the market's direction. MG comes before data, so data sprints build on finished identity, policy, approvals and receipts.
- **One approval model, defined in 019.** Access requests (024) reuse it. Until 019, an over-limit action is a deny.
- **Receipts early.** Receipts v2 (017) comes before policy (018) and approvals (019). Their fields arrive as record v2 extensions, so the receipt format does not change.
- **Read in place first.** 021 connects client data without copying. The lakehouse (022) is for data we must hold.
- **Purpose before grants.** The purpose stage arrives in 018. 024 binds purpose to grants.
- **Guardrails before agents read data.** 019 comes before the data agents (027). Taint and the trifecta breaker start in 027.
- **Insights after the semantic layer.** Dashboards and reports use the same governed metric path as the agent (025). There is no second query path for people.
- **Lineage after enforcement.** 025 needs decision ids from 024 reads.

## Old to new
| Old | New | Old | New | Old | New |
|---|---|---|---|---|---|
| 011, 012 | 011 | 023, 024 | 024 | 037 | 028 |
| 013 | 012 | 025, 026 | 025 | 038 | 019 |
| 014 | 013 | 027 | 027 | 039 | 028 |
| 015 | 014 | 028, 029 | 029 | 040, 041 | 017 |
| 016 | 021 | 030 | 026 | 042, 043 | 030 |
| 017, 018, 019, 020 | 022 | 031, 032 | 018 | 044 | 028 (spans, collector), 030 (audit analytics) |
| 021, 022 | 023 | 033 | 016 | 045, 046 | 032 |
| | | 034 | 019 | | |
| | | 035, 036 | 020 | | |

## What each sprint pack holds
Every `planning/sprints/NNN-slug/` folder holds `requirements.md` (scope, out of scope, questions closed), written from this map and the archived packs.
- **The next two sprints** also have the full set: `blueprint.md`, `acceptance.md`, `threat-model.md` and `builder-brief.md` (see `sprint-template.md`).
- **Later sprints** get the full set when they become next. The Architect writes it from the archived packs named in "From old" and the research in `review.md`, so it matches the code as it is then.

The Builder adds `build-log.md`, `report.md` and `evidence/`. QA adds `qa-review.md`.

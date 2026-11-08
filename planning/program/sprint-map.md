# Sprint map: 011 to 032

Milestones, not dates. A sprint is done when its acceptance checks pass and QA signs off. Feature sprints are vertical slices: the contract first (OpenAPI under `/v1`), then backend, then UI, then at least one e2e test across both.

**History.** The first draft had 20 sprints. Six reviews split it into 34, and the owner review made it 36. On 2026-10-11 the owner set a new direction ([Program 2 direction in `DECISIONS.md`](../DECISIONS.md)), and the map became 22 sprints. On 2026-11-02 an independent planning audit led to a re-plan for the **earliest sellable gateway** (owner decision, see `MAP.md`):
- M0 is local. The first real cloud run moves to a later milestone.
- 014 and 015 are trimmed to what the M0 journey needs. Their other work moves to the sprint that first uses it.
- The gateway sprints run in the order 016, 019, 020, 017, 018. Each is slimmed. SIEM export, audit search, showback, signed images and a pen test move into MG.
- Gateway breadth (per-stage evidence, guardrails on model calls and output, an OpenAI-style API with streaming, virtual models, an MCP upstream proxy, a Gateway Test screen, a guardrail console, central sign-in) is written into the owning sprints as plain requirements.

**Sprint numbers are ids, not order.** Folders, ADRs and links use the numbers. The **Run** column gives the order.

## The three pillars
| Pillar | What it covers | Modules |
|---|---|---|
| **Gateway** (security) | Identity, policy, guardrails, approvals, evidence and receipts, the protocol front (MCP, LLM API, A2A). Mature as a product on its own. | M1, M2 |
| **Data** | Connections to client sources and warehouses, lakehouse, pipelines, contracts, quality, grants, lineage, semantic layer, retrieval, grounding, BI. | M4, M5, M6 |
| **Agents** | Execution, sandboxes, our agents and templates, client and external agents, monitoring, memory. | M3 |

The Kernel (platform) sits under all three. **Integration first** holds in every pillar. Clients connect their own agents, sources, streams and warehouses through existing connectors, and all of them are governed the same way through the gateway.

## Milestones
| Milestone | Sprints (run order) | Showcase journey (script + Playwright e2e on the reference company) | Tag |
|---|---|---|---|
| **M0 Foundations** | 011, 012, 013, 014 and 015 | `poc up` brings the stack up locally from one command. A model call (local or hosted) is denied by policy before any inference, and the receipt names the model and lists every stage. Modules can be switched off. `poc backup`, `poc down` and `poc up` restore the stack with its signing key. | `v0.15.0` |
| **MG Gateway product** | 016, 019, 020, 017, 018 | An OpenAI-style client and an MCP client call through the gateway, with streaming. A PII prompt is masked and a tool call waits for a human approval. An SSO user in Finance may use a hosted model, an intern only the local one. Decisions stream to a SIEM and can be searched. Every decision has a COSE receipt anchored outside the host, and "why was this allowed" replays offline. Images are signed with an SBOM, the added latency is measured against a stated target, and a pen test of the gateway surface is clean. | `v0.20.0` |
| **MD Data on the client's stack** | 021 to 026 | A client Postgres and a CSV folder are connected in place, with no copy. A steward certifies a product with a contract. An analyst requests access with a purpose and reads masked rows. Lineage shows every step. A policy document question is answered with span citations, or the system abstains. | `v0.26.0` |
| **MA Agents and insights** | 027 to 029 | "What was Q3 gross margin by region?" is answered in a sandbox, with metric, snapshot and masked columns in the receipt. An integration agent maps a newly connected CRM schema, and a human approves it. A runaway agent is stopped by its budget breaker. A finance dashboard shows different numbers to two viewers, and every tile has a receipt. | `v0.29.0` |
| **ME Enterprise readiness** | 030 to 032 | An auditor exports a signed evidence pack and verifies it offline. A failover drill meets the stated RPO and RTO targets on a cloud. Each edition installs on its own and passes its smoke tests. | `v1.0.0` |

**Sellable point.** At the end of MG (`v0.20.0`), the Gateway and Assurance editions stand on their own. They govern our agents and the client's existing agents and tools, with signed receipts, SIEM export and a measured latency. This is the earliest product for security POCs.

**Freeze point.** If time runs out, the tag after 027 (`v0.27.0`) is a complete first version. It gives the full chain from a client source row, read in place, to a signed agent answer.

## Sprint list
| # | Run | Slug | Pillar | Goal | Depends on | ADR |
|---|---|---|---|---|---|---|
| 011 | 1 | `baseline-and-stack` | Platform | Planning drift fixed, exact pins and the licence gate, SBOM, secret scan, threat-model template. Valkey, Apache Kafka (optional profile) and SeaweedFS replace non-OSI parts. Ports bound to localhost, compose healthchecks and profiles. | — | — |
| 012 | 2 | `pillars-and-boundaries` | all | Evidence core split out of the gateway. Modules mapped to the three pillars. Cross-module ports, import-linter contracts, `ENABLED_MODULES`, module registry, edition smoke matrix. Decision record v2. Single tenant per deploy by default, RLS as defence in depth. | 011 | ADR-0013 |
| 013 | 3 | `models-and-providers` | Gateway | Local models pinned by digest. Hosted providers (Azure OpenAI, Bedrock, Anthropic, OpenAI-compatible vLLM) as an equal option through LiteLLM. Data-use and residency register, region pin in policy (`local` resolves to the deploy's declared region). Model identity and a signed per-stage list (`stages`) in every record. Model calls get an input guardrail. Virtual models: fallback only inside the allowed regions, a breaker per route, a concurrency cap per tenant. A request-level admission check before any inference. A decision-path benchmark (decisions per second, added p50 and p95 latency). | 012 | ADR-0014 (revised) |
| 014 | 4 | `reference-company` | Platform | The M0 showcase only: personas with keys, the `m0.sh` script (every M0 step, ending with the 015 restore drill) and the M0 Playwright project. Data generators move to 021. | 013, 015 | — |
| 015 | 3 (parallel with 013) | `cloud-poc-lifecycle` | Platform | Local lifecycle only: release manifest with images pinned by digest, `poc up/backup/down/status` on the local host, maintenance mode, backup and restore that keep the signing key, a restore drill with a real run. OpenTofu, cloud modules and the upgrade job move to the cloud track. | 012 | ADR-0032 |
| 016 | 5 | `gateway-service-and-proxy` | Gateway | The request contract every agent call carries, agent registry with a kill switch, `authorize()` over `enforce()`. OpenAI-compatible `/v1/chat/completions` (with SSE) and `/v1/embeddings` over the 013 model caller, streaming in `buffer_all` mode. MCP 2026-07-28 front, and an MCP upstream proxy with a tool allowlist, pinned tool hashes and per-server credential brokering. `cost_centre` on records and a showback view. Gateway Test screen that shows each stage from the signed record. A stated latency and throughput target, proven by a load test. | 013 | ADR-0023 (revised) |
| 019 | 6 | `guardrails-and-approvals` | Gateway | A guardrail port with an ordered chain bound per action and direction in tenant policy. Presidio on input and output, a secrets recognizer, regional identifiers as data, a re-selected local guard model with its digest in records. Stream modes (`buffer_all` default, `windowed_scan` opt-in and documented as best effort). Guardrail console: library, bindings, activity. The one approval model bound to the canonical action hash, the inbox, stop and override. AI-generated content disclosure (EU AI Act Art. 50). | 016 | ADR-0024, ADR-0027 |
| 020 | 7 | `identity-and-access` | Gateway | Keycloak OIDC sign-in for the console (code flow with PKCE into our session; keys stay for machines), MFA through realm config, custom roles, a read-only auditor role. Subject-scoped policy: rules by user, group, role and agent id, in both the policy document and the decision table. Platform-minted delegation tokens that only narrow, with token-issuer key rotation. | 019 | ADR-0025 |
| 017 | 8 | `receipts-v2-and-anchoring` | Gateway | COSE_Sign1 receipts (RFC 9942 proofs) with `kid`. Signing-key port with a file adapter, rotation and revocation list. One external anchor (public RFC 3161 TSA or Rekor) on by default. Standalone verifier package with test vectors. Audit search and export (CSV, JSON). SIEM export as OCSF to syslog or Splunk HEC, with no collector dependency. | 020 | ADR-0029, ADR-0030 |
| 018 | 9 | `policy-engine-and-replay` | Gateway | The Python policy engine as a small, versioned, pure package that the verifier can import, pinned by hash in the record. Replay and what-if of "why was this allowed" offline. Purpose stage. AuthZEN 1.0 API with interop tests. MG close: cosign-signed images with an SBOM attestation, and a pen test of the 016 to 020 surface. | 017 | ADR-0022 |
| 021 | 10 | `data-access-and-federation` | Data | Reference data generators first (finance, CRM, HR, PDFs, a client source in its own container, a change generator). `DataAccess` adapters: Direct (DuckDB ATTACH, read-only), Lakehouse (DuckLake), Federated spike (Trino). Connection registry with credentials from the secret store. `data.read`, snapshot ids in records, SQL parse base (sqlglot). | 018 | ADR-0015 (revised) |
| 022 | 11 | `connectors-pipelines-transforms` | Data | dlt sources, lakehouse write path (single writer, protected snapshots, retention, erasure, backups), pipelines on the job queue, dbt on DuckLake, client event streams (optional profile). | 021 | ADR-0016, ADR-0017 |
| 023 | 12 | `products-contracts-quality` | Data | Data products (ODPS 1.1) and contracts (ODCS 3.2), versions and breaking-change diff, classification, glossary, catalog search and import. Contract rules compiled into policy data. Checks, certification, quality score, freshness SLOs. | 022 | ADR-0018 |
| 024 | 13 | `grants-and-query-enforcement` | Data + Gateway | Access requests with purpose on the 019 approval model, grants, expiry, revocation. Grants enforced by rewriting SQL (row filters, column masks), minimum group size, cache keys with grant version, bypass corpus. | 023 | ADR-0019 |
| 025 | 14 | `lineage-and-semantic-layer` | Data | Lineage store, OpenLineage from pipelines, dbt and streams, agent facets, decision ids through `EvidenceLookup`. MetricFlow compile, rewrite, guard. Parsed SQL guard with a function allowlist and an injection fuzz corpus. | 024 | ADR-0020, ADR-0021 |
| 026 | 15 | `documents-retrieval-grounding` | Data | Docling offline, true BM25 beside pgvector, per-chunk ACLs, grounding gate with span citations and abstention, labelled eval set, client pgvector adapter, malicious-PDF test. | 025 | ADR-0033 |
| 027 | 16 | `data-and-integration-agents` | Agents | Agent tools on `DataAccess`, sandbox mandatory, session taint and the lethal-trifecta breaker, answer receipts, Ask-data UI, nightly red team. Integration agents that map a new connection for a human to approve. | 026 | — |
| 028 | 17 | `agent-registry-monitoring-memory` | Agents | A2A v1.0 with signed Agent Cards and delegation tickets that only narrow. One registry for our, client and external agents. W3C trace context and one span per gateway stage, OTel GenAI spans with `decision_id`, the collector, loop and budget breakers, governed memory. | 027 | ADR-0026, ADR-0028 |
| 029 | 18 | `insights` | Data | Metric catalog, dashboards read under the viewer's grants with a receipt per tile, reports per recipient, metric alerts. | 028 | ADR-0031 |
| 030 | 19 | `evidence-packs-and-siem` | Gateway | Signed evidence packs, retention floor, system and model cards, ML-BOM, EU AI Act, ISO 42001, NIST and OWASP mappings backed by tests. Enterprise identity deferred from 020: SCIM deprovisioning, IP allowlist, SPIFFE run ids. OPA adapter with a parity suite. Approval webhook (Jira, ServiceNow). | 029 | — |
| 031 | 20 | `resilience-and-cloud` | Platform | The cloud track lands here at the latest: OpenTofu interface, first cloud VM module, upgrade-from-previous-release job. RPO and RTO targets with a failover drill, HA reference, encryption at rest, KMS and PKCS#11 signing adapters, local TSA and transparency log, OpenBao secrets, one Helm chart. | 030 | ADR-0034 |
| 032 | 21 | `release-and-trust` | Platform | Per-edition packages and installs, air-gap bundle, WCAG 2.2 AA checks and an ACR, CAIQ v4 answers, `security.txt` and disclosure policy, exit runbook, a scripted walkthrough of every milestone. | 031 | — |

## Tracks outside the sprint map
- **Cloud track.** The OpenTofu interface, the first cloud VM module and the upgrade job start when the owner names a provider, or a client POC needs a cloud. At the latest they land in 031.
- **POC kit.** Planned with the owner first, because the client data shape is unknown. The earliest it can start is after MG.
- **Portfolio.** 2–3 public projects in their own repos, with no private code. Not part of this map.

## Order notes
- **Land before building on top.** 013 builders start after the 011 and 012 commits are approved and landed.
- **Gateway first.** MG comes before data, so data sprints build on finished identity, policy, approvals and receipts.
- **Breadth before depth in MG.** The proxy (016) and guardrails (019) are what a buyer tries first. Identity (020), receipts v2 (017) and replay (018) follow. New receipt fields arrive as record v2 extensions, so the receipt format does not change when 017 lands later.
- **One approval model, defined in 019.** Access requests (024) reuse it. Until 019, an over-limit action is a deny.
- **Streaming is guarded from day one.** 016 ships only `buffer_all`. 019 adds `windowed_scan`.
- **Measure the hot path early.** 013 adds the benchmark. 016 states the target. If the per-tenant chain lock caps throughput below it, the fix (chain sharding or batched linking, both fail closed) is decided before 016 ships.
- **Read in place first.** 021 connects client data without copying. The lakehouse (022) is for data we must hold.
- **Purpose before grants.** The purpose stage arrives in 018. 024 binds purpose to grants.
- **Guardrails before agents read data.** 019 comes before the data agents (027).
- **Insights after the semantic layer.** Dashboards and reports use the same governed metric path as the agent (025).

## Moved by the 2026-11-02 re-plan
| Item | From | To |
|---|---|---|
| Reference data generators, PDFs, client source, change generator | 014 | 021 |
| OpenTofu interface and modules, cloud VM run, upgrade job | 015 | cloud track, 031 at the latest |
| Cross-encoder reranker port, nightly model workflow, GPU and hosted profile docs | 013 | later, when a client needs them |
| agentgateway spike, Cilium and Kubernetes egress templates, private signed-manifest registry | 016 | 028 |
| Approval webhook, AuthZEN approval profile | 019 | 030 |
| SCIM deprovisioning, IP allowlist, SPIFFE ids, token-exchange spike | 020 | 030 |
| Local TSA, per-tenant transparency log, PKCS#11 and cloud KMS signing | 017 | 031 |
| OPA runtime adapter and two-engine parity suite | 018 | 030 |
| SIEM export (OCSF), audit search and export | 030 | 017 |
| `cost_centre` and showback | 030 | 016 |
| Image signing with SBOM, pen test of the gateway surface | 032 | 018 |

## Old to new (36-sprint draft)
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
Every `planning/sprints/NNN-slug/` folder holds `requirements.md` (scope, out of scope, questions closed).
- **The next two sprints in run order** also have the full set: `blueprint.md`, `acceptance.md`, `threat-model.md`, `test-spec.md` and the builder brief.
- Every work package in a test spec or brief names the milestone journey step it moves. Hygiene work is capped at about 20% of a sprint.
- **Later sprints** get the full set when they become next, written against the code as it is then.

The Builder adds `build-log.md`, `report.md` and `evidence/`. QA adds `qa-review.md`.

# Plan review: six perspectives

On 2026-10-08 the first draft (20 sprints) was reviewed by six independent reviewers. Each read the plan, the code and the planning files. This file lists what they found and what changed. The current plan already includes every change marked "done".

## 1. Security architect
| Finding | Severity | Change | Where |
|---|---|---|---|
| Lakehouse isolation was only logical. One DuckDB connection with the catalog and one S3 key could read every tenant. | Critical | One catalog, data prefix and S3 identity per tenant. Locked connections. Cross-tenant negative tests (schema, path, `read_parquet`, `ATTACH`, `COPY TO`). | 016 |
| DuckDB views are not a security barrier. The SQL fallback was an injection surface. | Critical | Parsed SQL, one SELECT, function allowlist, typed filters, rewrite to granted relations, fuzz corpus of 50+ cases. | 024, 026 |
| Agents read data and untrusted documents before guardrails existed. | Critical | Taint, trifecta breaker, link and image stripping, mandatory sandbox for data agents moved to 027. Malicious-PDF test in 030. | 027, 030 |
| CDC credentials and an open Kafka Connect API. | High | Replication-only role, filtered publication, secrets via config provider, port 8083 not published, SASL and ACLs, tenant from registration. | 020 |
| Grant and approval races. | High | Approval bound to the canonical action hash, single use, re-checked at execution, separation of duties, cache keyed by grant version, revocation cancels running queries. | 023, 024, 034 |
| Confused deputy in token exchange, MCP token passthrough, tool poisoning. | High | `may_act`, nested `act`, audience limits, narrowing only. No passthrough. Tool definitions pinned by hash. | 033, 036 |
| Supply chain arrived in the last sprint. | High | SBOM, hash-locked deps, image digests, secret scan in 011. Model digests in 014. Vendored dbt packages in 019. Offline models in 030. | 011, 014, 019, 030 |
| One receipt key, local TSA on the same host. | High | Separate keys, file-mounted secrets, PKCS#11 slot, rotation drill, `kid`, warning when no external anchor. | 040, 041 |
| No threat model per sprint; OWASP ASI tested only at the end. | Medium | `threat-model.md` in every pack. ASI items tested in the sprint where the risk appears; 043 only collects them. | all |
| SSRF in the HTTP connector, upload limits, telemetry leaks, small-group inference, event spoofing. | Medium | Egress allowlist and private ranges denied (018), upload limits (017), hashes not literals (025, 044), minimum group size (024), tenant checked against source registration (020). | various |

## 2. Data engineer
| Finding | Severity | Change | Where |
|---|---|---|---|
| Wrong assumption: DuckLake handles concurrent writers. Some conflicts abort. | High | Single writer per table, advisory lock, retry wrapper, API never writes. | 017 |
| DuckDB process model undefined. | High | Thread pool for reads, query worker for heavy queries, writes only in workers. | 016 |
| Wrong assumption: per-grant views are enough and cheap. | High | Rewrite SQL at compile time. Check that file pruning still works. | 024 |
| Snapshot pinning conflicts with retention and erasure. | High | Protected snapshots, maintenance job, erasure flow that records unreplayable receipts. | 017 |
| CDC sink not designed. | High | Micro-batches, dedupe by key, LSN guard, offsets in the same DuckLake transaction, deletes, snapshot handoff, schema change rules, WAL growth alert. | 020 |
| dbt runs are unisolated code. | High | Generated per-tenant projects, no user SQL until sandboxed, short-lived profiles, OpenLineage support proved by a spike. | 019 |
| MetricFlow would bypass grants. | Medium | Compile only, then rewrite and guard. Spike first, curated SQL metrics as fallback. | 026 |
| Contract versions, quality scoring, seed data, orchestration history, backups, schema evolution, snapshot UI, catalog search. | Medium/Low | Added to the sprints named. | 015, 017, 018, 021, 022 |

## 3. Platform, operations and licences
| Finding | Severity | Change | Where |
|---|---|---|---|
| Docker Desktop is not open source. | High | Docker Engine in WSL or Podman, pre-flight check. | 012 |
| Valkey breaks the semantic cache without code changes. | High | valkey-bundle 9.1.3 with search 1.2.1, three code changes, new volume, pgvector fallback, CI images replaced. | 012 |
| Memory budget did not fit 16 GB. | High | Real budget, Ollama limits, DuckDB `memory_limit`, profiles per task, measured each sprint. | `stack.md`, all |
| CPU inference too slow for agent loops at 4B with thinking mode. | Medium | Instruct model without thinking on CPU, smaller models for routing, fake model in CI, nightly 0.6B smoke. | 014 |
| Guard model supply chain (third-party GGUF). | Medium | Granite Guardian from the official library, `models.lock`. | 014, 038 |
| Hidden non-OSI or cloud parts: `ollama/llama3` fallback, gitleaks Action, telemetry, runtime downloads, cloud defaults. | Medium | Each assigned to a sprint (011, 014, 030, 038). | various |
| Ports open on the LAN under mirrored networking. | Medium | Bind to `127.0.0.1`. | 012 |
| CI minutes and service containers that need commands. | Medium | Concurrency cancel, path filters, `.venv` cache, compose `--wait` steps, nightly jobs for heavy services. | 011, 020, 035 |
| Backups of catalog and files as one set; keys and the log are critical. | Medium | Runbooks in 017, 041, 045. | 017, 041, 045 |

## 4. AI governance and standards
| Finding | Severity | Change | Where |
|---|---|---|---|
| Purpose and taint arrived after agents read data. | High | Purpose stage in 024, taint in 027. | 024, 027 |
| Retention below the EU AI Act six-month minimum. | High | `high_risk` flag raises the floor to 183 days. | 042 |
| Every sprint would change the chain hashing. | High | Decision record v2 with `record_version` in 013. | 013 |
| Keycloak v2 exchange may not emit `act`. | High | Spike on day one, platform-minted delegation tokens as fallback. | 036 |
| MCP elicitation needs the new transport. | High | MCP 2026-07-28 (033) moved before approvals (034). | 033 |
| Draft standards treated as final. | Medium | Labels: AuthZEN 1.0 final; approval and MCP profiles "draft-compatible"; OTel GenAI opt-in; facet schemas published. | 032, 033, 034, 044 |
| Evidence packs missing artifacts. | Medium-High | System card, model cards and ML-BOM, ISO 42005 and FRIA templates, oversight and incident logs, SoA, NIST profiles, signed pack. | 042, 043 |
| Evals too thin, red team too late. | Medium-High | Result-set evals, abstention and leakage tests, nightly red team from 027, three CI tiers, signed eval records. | 027, 038, 043 |
| Differentiators to add. | Medium | Replay of "why allowed", policy what-if, pinned tool definitions, attestation fields, receipts that state what was withheld. | 027, 031, 032, 033, 040 |

## 5. Product and modularity
| Finding | Change | Where |
|---|---|---|
| The code is layered, not split by module, and the gateway needs the evidence core. | Boundaries in 013. Evidence core ships with the gateway. Cross-module ports with no-op adapters. Editions table. Edition smoke matrix in CI. | 013 |
| No shared sample domain. | One fictional reference distributor used for every showcase and eval. | 015 |
| No console information architecture. | `docs/design/IA.md` in 013: Workspace, Data, Governance, Evidence, Platform. Nav hides disabled modules. Each pack names its nav placement. | 013 |
| Twenty sprints too many; suggested cuts. | Not cut: the owner asked for the full architecture. Instead: smaller sprints, a freeze point after 027 (moved to 028 in the owner review), and milestones that each stand alone. Superset deferred. | `sprint-map.md` |
| Wording: README listed a missing file; STATE is stale. | This file now exists. STATE fixed in 011. | 011 |

## 6. Delivery lead
| Finding | Change | Where |
|---|---|---|
| Sprints were twice the size of 009 and 010. | Split into 34 sprints of about five items each. | `sprint-map.md` |
| Plan facts that conflict with the code: latest migration 0010, scheduler only runs retention, cache needs search, CI pins Redis Stack, the policy seam exists, `data.read` is a new action kind, Ollama already in compose, `mcp` unpinned, `check_skips.py` hard-codes MinIO, new SDKs must join the import lint, Debezium needs `wal_level=logical`, `setup_db.sh` lacks the lakehouse database, `AGENTS.md` stack is stale. | Each fact is written into the sprint that touches it. | 011–020 |
| Open questions not mapped. | Mapped in `sprint-seeds.md` (Q1, Q8, Q20, Q22, Q26–Q29, Q31, Q34–Q37, Q40–Q46). Hosting questions stay parked. | packs |
| Branching plan did not match how 005–010 were committed. | Branching file explains the change and archives `COMMIT_PLAN.md`. Commit blocks are guidance (3 to 8). | `branching-and-commits.md` |
| Test pattern for new components. | Contract suite, fake, live verify script, skip allowlist. Table in `sprint-template.md`. | all |

## Owner review (2026-10-09)
| Finding | Change | Where |
|---|---|---|
| The data side had no business intelligence: no dashboards, reports or alerts for people. | New module M6 Insights with two sprints: governed dashboards (028) and reports and alerts (029). The freeze point moves to `v0.28.0`. Sprints 028–044 became 030–046. | `sprint-map.md`, `vision-and-architecture.md`, ADR-0031 |
| External BI servers would bypass the gateway. | BI is built in, on the same metric path as the agent. External tools wait for a governed SQL endpoint (program 3). | `stack.md` |

## Coherence audit (2026-10-09)
Four read-only reviews checked the whole plan: stack and licences, names and contracts, sprint order and references, and architecture rules. The renumbering was clean. The fixes:
| Area | Finding | Change |
|---|---|---|
| Ports | `DataAccess` was named but never specified; M6 and M3 needed methods it lacked | One port that grows by sprint (`conventions.md`). `LineageLookup` added in 025. |
| Boundaries | M6 was told to reuse M4 code; the inbox sat in a module | M6 uses ports and kernel only. The inbox is kernel. |
| Receipts | A tile cache could return numbers with no decision | No tile cache. The 024 cache sits behind `enforce()`. |
| Snapshots | Per-dataset snapshot maps, but DuckLake snapshots are catalog-wide | One snapshot id per view, run and answer. |
| Purpose | Dashboards and reports carried no purpose | Dashboards declare a purpose. |
| Events | Alerts listened to the knowledge-base ingest event; lake writes emitted nothing | `platform.data.snapshot.committed.v1` from the 017 write path. One naming rule for events. |
| Identity | Scheduled reports had no valid principal under SSO | `on_behalf` in 029, staleness in 035, delegation in 036. Keycloak delegation is a preview feature. Decided 2026-10-11: platform-minted by default. |
| Names | Duplicate reason codes, two self-approval codes, route and setting drift | One name each, recorded in `conventions.md`. |
| Resources | The MC journey did not fit 16 GB; some services were not counted | `memory=12GB`, MC split into two journeys, full memory table. |
| Licences | Missing PyPI metadata, red-team tools pulling large trees, dual-licensed Docling weights | Reviewed override file, separate red-team venv, weights decision in 030. |

## Five-direction review and owner direction (2026-10-11)
The earlier reviews all leaned the same way. They fixed details but did not question the direction. So five new read-only reviews each took a different angle: enterprise buyer, market and competitors, contrarian architecture, client data and POCs, and portfolio. Then the owner set the direction (`DECISIONS.md`, "Program 2 direction"). Five research notes followed on how to act on the findings: integration and connectors, gateway proxy and agents, cloud and portability, enterprise gaps, and the data pillar. The full notes, with sources, are in the owner's project vault. The table lists what changed.

| Finding | Change | Where |
|---|---|---|
| The plan copied client data into our lakehouse. Clients will not move finance or HR data. | Integration first. `DataAccess` adapters: Direct, Federated (Trino + OPA), Lakehouse, Native. Rule 12. | 021, 024 |
| The gateway was in-process only, so it could govern only our own agents. | `authorize()` service and three deployment modes (embedded, sidecar, standalone proxy). One request contract for every agent. Rule 11. | 016 |
| Our edge is proofs, not logs, but receipts and replay came last. | Receipts v2 and anchoring moved to 017, replay to 018. One external anchor on by default. Standalone verifier. | 017, 018 |
| Design target was a 16 GB laptop; no deploy or upgrade path until the end. | Cloud POC lifecycle with OpenTofu in M0. Upgrade-from-previous-release CI job. | 015, 031 |
| Multi-tenant SaaS design for single-client POCs. | Single-tenant per deploy is the default; RLS stays. | 012 |
| Hosted models were second-class. | Local or hosted is the client's choice, with a provider data-use and residency register. | 013 |
| Buyer gaps: HA and RPO/RTO, encryption at rest and keys, secrets manager, SCIM, MFA, custom and auditor roles, SIEM, chargeback, WCAG, air-gap, exit plan, ticketing hook, vendor trust pack. | Each placed in a sprint. Keycloak 26.8 brings SCIM. OpenBao instead of Vault. OCSF and Splunk HEC for SIEM. CAIQ v4 and a pen test for vendor trust. | 019, 020, 030, 031, 032 |
| Guardrail vendors were acquired by large security firms. | A guard-provider port, so a third-party verdict lands in our receipt. | 019 |
| Catalogs exist at the client (OpenMetadata, DataHub). | Import their catalog and lineage instead of competing. | 023, 025 |
| The "BM25" leg is Postgres `ts_rank` (`adapters/pg_knowledge.py:65`). There are no per-document ACLs. | Rename in 011. True BM25 (`pg_textsearch`), per-chunk ACLs and a grounding gate in 026. | 011, 026 |
| Agent monitoring arrived at the end, with observability. | Registry with a stop flag in 016. Spans, breakers and stop-run in 028. | 016, 028 |
| Too many moving parts for one maintainer. | Kafka and Debezium are optional profiles. Trino is its own profile. Mailpit stays optional. | 011, 022 |
| 36 sprints. | 22 sprints, gateway first. Sellable point `v0.20.0`, freeze point `v0.27.0`. | `sprint-map.md` |
| Licence traps found: Airbyte (ELv2), SDV (BSL), Terraform and Vault (BSL), ParadeDB (AGPL). LiteLLM licence and incident reports unverified. | Added to "Rejected" in `stack.md`. LiteLLM is checked in 011. | `stack.md`, 011 |

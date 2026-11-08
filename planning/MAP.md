# Platform map

The one entry point for the owner and every model. Read this first. It replaces `STATE.md`.
Hard limit: 160 lines, and "Now" at most 15 lines; a test enforces both. History goes to sprint reports and `CHANGELOG.md`, not here.
Owner view: the same content as an HTML page, https://claude.ai/artifact/X1LuqfsbGrCb2Ynucy8711 (source `scratch/map/map.html`). Updated by the Architect whenever a status, decision or plan changes.

## North Star
**Proof from source row to agent answer.** Every answer can be traced to the data it read, the policy that allowed it and a signed receipt that anyone can verify offline.
- Three pillars on one kernel: **Gateway** (security, sellable on its own), **Data** (the client's sources read in place, plus a lakehouse only where needed), **Agents** (sandboxed execution and monitoring).
- Integration first: govern the client's existing agents, sources and warehouses. Do not rebuild them.
- Every agent (ours, the client's, external) reaches models, tools and data only through the gateway.
- Built on open-source components, with no third-party licence fees. Our code is private.

## Rules that decide every trade-off
1. One door: every model, tool and data call goes through `enforce()`, and every decision is recorded. A failed record means a deny.
2. The server is the authority. The UI hides what is off and shows what the server decided.
3. Modules import only the kernel and `ports/` (import-linter in CI). Editions are selected with `ENABLED_MODULES`.
4. Standards over inventions: OpenAI-style API, MCP, A2A, AuthZEN, OpenLineage, ODCS, COSE/SCITT, OTel.
5. Each work package names the milestone journey step it moves. Hygiene work is capped at about 20% of a sprint.
6. No workaround in product code. A local workaround lives in `scratch/`, is labelled, and has an end date.
Full rule set: `planning/program/vision-and-architecture.md` (13 program rules) and `AGENTS.md` (15 strict rules).

## Where the authority lives
| Topic | Document |
|---|---|
| Vision, modules, ports, request path, design rules | `planning/program/vision-and-architecture.md` |
| Sprints 011 to 032 and milestone journeys | `planning/program/sprint-map.md` |
| Console screens per sprint | `planning/program/ui-delivery.md`, `docs/design/` |
| Architecture decisions | `docs/adr/` (0001 to 0012 and 0035 written, 0013 to 0034 planned) |
| Owner decisions and open questions | `planning/DECISIONS.md`, `planning/QUESTIONS.md` |
| How builders work and are reviewed | `planning/program/builder-method.md`, `review.md` |
| One sprint | `planning/sprints/NNN-slug/` (requirements, blueprint, acceptance, threat model, test spec, builder brief) |
| Superseded, kept for reference | `planning/history/` (old root plans archived there 2026-11-02) |

## Feature map
Status: **built** (on `main`, QA signed) · **local** (built and verified, not committed) · **next** · **planned** (sprint).

| Module | What it does | Status |
|---|---|---|
| Kernel | Postgres with forced RLS, Valkey, object store (local, S3, SeaweedFS), durable jobs and workers, outbox (Kafka optional), identity (API keys, JWT, sessions, run tokens), settings, metrics | built |
| Kernel: models | One model per mode through LiteLLM | built; pinned digests, hosted providers, region and data-use pins, breakers, admission check: 013 |
| M1 Gateway: core | `enforce()` with principal, module, boundary, policy, input guardrails, rate, budget, cost stages; tenant JSON policy | built (module stage: local); per-stage evidence and model stage: 013 |
| M1 Gateway: protocol front | MCP server for clients | built |
| M1 Gateway: proxy | Embedded and standalone modes (sidecar later), OpenAI-style API with streaming, stateless MCP, MCP upstream proxy with credential brokering, agent registry, kill switch, showback, Gateway Test screen, latency target | planned 016 |
| M1 Gateway: policy | Python engine as a pinned package, offline replay, purpose stage, AuthZEN API; signed images and pen test close MG | planned 018 (optional OPA: 030) |
| M1 Gateway: guardrails | Ordered guardrail chain in and out, Presidio, secrets, stream modes, guardrail console, approvals bound to the action hash, inbox | planned 019 (today: regex on KB reads and agent runs; model calls: 013) |
| M1 Gateway: identity | OIDC client for any provider, SCIM 2.0, Entra group overage, roles, subject-scoped policy, delegation tokens; Keycloak only for tests | planned 020 (IP allowlist: 030) |
| Evidence core | Decision record per call, per-tenant hash chain, Ed25519 receipts, offline verifier | built; record v2 with extensions: local |
| M2 Evidence | COSE receipts, external anchor, audit search, SIEM export (OCSF) | planned 017; evidence packs 030; transparency log and KMS 031 |
| M3 Agents | LangGraph agent, OpenShell sandbox, run tokens, agent runs page | built (thin agent) |
| M3 Agents: run state and skills | Checkpointed runs that resume after a crash, approval as interrupt and resume, governed skills a human approves | planned 027 |
| M3 Agents: registry and monitoring | A2A, signed Agent Cards, OTel GenAI spans, breakers, governed memory, consolidation job, outside harnesses through the gateway | planned 028 |
| M4 Data plane | Direct and federated access on DuckDB (Trino optional), lakehouse, CDC by logical replication or dlt, pipelines, products, contracts, grants by SQL rewrite | planned 021 to 024 |
| M5 Lineage, semantic layer | OpenLineage, agent facets, OSI metric definitions compiled by MetricFlow | planned 025 |
| Documents and grounding | Docling, BM25, ACL per chunk, abstention | planned 026 (today: hybrid retrieval, citations) |
| M6 Insights | Metrics, dashboards and reports under the viewer's grants | planned 029 |
| Editions | Sold: Gateway, Gateway + Data, Full. Five module sets as CI profiles with a smoke test each | sets built (012); sold editions: re-plan 2026-11-08 |
| Console | Overview, Ask, Library, History, Requests, Decisions, Policies, Keys, Usage, Agent runs, Modules, Trust, System | built; Modules page: local |
| Reference company and showcase | Personas and the M0 script (014); fictional distributor data (021) | next 014 |
| POC lifecycle | Local `poc up/backup/down/status`, maintenance mode, restore drill (015); OpenTofu and cloud VM: cloud track, 031 at the latest | next 015 |

## How it connects (target request path)
User or agent → credential gives tenant → gateway admits the run (principal, boundary, policy, purpose) → agent runs in the sandbox with a run token → metric compiled to SQL → SQL guarded and rewritten to the grant → `DataAccess` reads at a pinned snapshot → output guardrails → `model.invoke` → receipt with SQL hash, snapshot, masked columns, policy hash and model digest → chain head anchored → lineage event links source to answer.
Built today: credential → gateway → agent or search → model → receipt and chain. Everything from SQL onward is planned (021 to 025).

## Milestones
| Milestone | Journey (the acceptance test) | Sprints | Status |
|---|---|---|---|
| M0 Foundations | `poc up` locally; a model call denied before any inference, receipt names the model and lists every stage; modules switched off; `poc backup`, `down`, `up` restores | 011 to 015 | 011 local-accepted, 012 closing, 013 to 015 packs re-planned |
| MG Gateway product | OpenAI-style and MCP clients through the gateway; masked PII; a human approval; SSO with subject policy; SIEM stream and audit search; anchored COSE receipts; offline replay; signed images; measured latency; pen test | 016, 019, 020, 017, 018 (run order) | planned; sellable point |
| MD Data | Client Postgres and CSV read in place; certified product; masked rows under a purpose; lineage; cited or abstained answer | 021 to 026 | planned |
| MA Agents and insights | Sandboxed margin question with metric and snapshot in the receipt; integration agent; budget breaker; dashboards per viewer | 027 to 029 | planned |
| ME Enterprise | Signed evidence pack; failover drill on a cloud; each edition installs alone | 030 to 032 | planned |

M0 journey steps today: modules off (done locally in 012) · deny by policy (done) · deny before any inference, receipt names the model and lists stages (013) · personas and `m0.sh` (014) · local `poc up/backup/down/up` (015).

## Agreed with the owner
- Three pillars, integration first, gateway first, single tenant per deploy by default, hosted models as an equal option (2026-10-11).
- 36 sprints condensed to 22. SCIM and SIEM are in the plan. Pins younger than 14 days are not used (security patches excepted, recorded per case).
- Builders are GPT-6 Luna through Codex; the Claude Architect plans, reviews and proves with real requests (2026-10-26, 2026-10-28).
- No commit or push without the owner's go.
- Gateway breadth (per-stage evidence, guardrails on model calls and output, OpenAI-style API with streaming, virtual models with breakers, MCP upstream proxy, Gateway Test screen, guardrail console, central sign-in, delegation tickets, spans per stage) goes into existing sprints as plain requirements, not new sprints (2026-10-30).
- Planning docs describe our product in our own terms: no names of, or comparisons with, other codebases (2026-11-02).
- 2026-11-08 re-plan (ADR-0035): only Postgres, Valkey, API and worker are required; every other service is optional behind a port, a setting and a parity test. No Debezium; Trino, OPA and Kafka optional; Keycloak test-only; three editions sold; sidecar later; lighter packs. Agents gain saved run state, governed skills, a consolidation job and governed outside harnesses.
- 2026-11-02, after the planning audit (`scratch/planning-audit.md`): re-plan for the earliest sellable gateway (trim 014 and 015; gateway order 016, 019, 020, 017, 018; SIEM, signing and pen test pulled into MG). M0 stays local; the first real cloud run moves to a later milestone. Per-stage evidence and the model-call input guardrail go into 013. The old root plans are archived; the Architect drafts a product map; the D: disk file is compacted. Commits for 011 and 012 are prepared after 012 passes; the owner approves them.

## Open for the owner
1. Sign off the 2026-11-08 re-plan diff, then the lighter 013 to 015 packs.
2. Shape the product map (end-state console) once the Architect's draft is ready.

## Now (2026-11-08)
- **011 and 012 committed locally** on `sprint/011-baseline-and-stack` and `sprint/012-pillars-and-boundaries`. Not pushed.
- **Re-plan 2026-11-08 written:** sprint map, program docs, stack, ADR-0035 and the 016, 020 to 022, 024, 025, 027, 028 and 030 requirements. Waiting for owner sign-off.
- **Next:** lighter 013 to 015 packs, then the owner's go for the 013 builder.
- Environment: Docker data disk is on D: (needs at least 25 GB free; check before pulls). Docker Desktop does not start at sign-in; start it after a Windows restart. Local Playwright: `scratch/pw/run.sh`.

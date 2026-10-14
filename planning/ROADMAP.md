# Roadmap

Milestones only, with no dates. Each sprint is done when its acceptance checks pass.

## Phase 1: polish (independent of the sprints below)
- Keep the hosted instance awake (parked with the other hosting items, see `QUESTIONS.md`).
- A walkthrough video.
- An open-source MCP server, possibly in its own repo.

## Foundation sprints
| Sprint | Title | Goal | Strict rules it enforces | State |
|---|---|---|---|---|
| 000 | Operating structure | Files-based planning, functional naming, `public-preview` mode | 14 (fail fast on config) | done |
| 001 | Foundation architecture | `FOUNDATION.md` and ADRs 0001–0005 (docs only) | Defines all 15 | done |
| 002 | Platform base | pydantic-settings config, an Alembic baseline, `/v1`, one error format, JSON logs with trace IDs, OTel traces, mypy in CI, lint cleanup, fix the pre-existing unit-test failures (Q B1, B2) | 7, 8, 10 (trace IDs), 14, 15 | done |
| 003 | Identity and tenancy | API keys and JWT resolve to a principal and a tenant; a `tenants` table, `tenant_id` and row-level security; namespaces become knowledge bases | 1, 2, 3 | done |
| 004 | Gateway core | The `enforce()` pipeline (authN, tenant, policy, guardrails, budget, audit) with a policy engine interface (Python first) and the existing rate-limit and budget middleware moved in; an ExecutionBoundary for agent tool calls | 3, 4, 5, 10 | done |
| 005 | Frontend foundation and showcase | TypeScript React SPA on Tailwind and shadcn/ui, a typed API client from OpenAPI, the governance console (Decisions explorer, Policies, Keys, Budgets, Agent runs), the workspace (Ask, Library, History), a web-edge cookie session (ADR-0007), read-only `/v1` console endpoints, and a public showcase landing page (GSAP, one lazy WebGL hero) | 1, 2, 3, 10 | done |
| 005b | Polish round | Ink-and-paper palette, the new landing copy and a hero built from real components, a How it works page, an Overview home, decisions grouped by request with a drawer, plain-language reason codes, a governance line in Ask, a guided walkthrough, a session menu, a Cmd+K palette, and route-level code splitting | 10 | done |
| 006 | Ports and adapters | Interfaces for the LLM, embeddings, vector store, object store and queue. An EventBus port (CloudEvents, ADR-0008) and an AgentRuntime port (start, status, stop, cleanup; in-process adapter by default, ADR-0009). Vectors record their model and dimension. An import-lint rule | 9, 12 | done |
| 007 | Durable jobs and raw storage | A Postgres-backed queue with retries, a dead-letter queue and idempotency keys. A transactional outbox behind the EventBus. Ingestion and agent runs move to workers. Raw files go to object storage by hash. The Library shows ingestion progress | 6, 11, 13 | done |
| 008 | Trust baseline | Audit receipts, an eval regression gate in CI, a cost circuit breaker, Prometheus metrics through OpenTelemetry (`/metrics`) with an optional Prometheus and Grafana compose profile, retention and purge for `gateway_decisions` (Q7), and the Trust pages in the UI | 10, 15 | done |
| 009 | Sandboxed agent execution | An NVIDIA OpenShell adapter for AgentRuntime (Apache-2.0, pinned v0.1.x). The agent completes an authorized task, can't reach a model provider directly, can't read unrelated files, and the gateway denies an unauthorized tool argument. OpenShell events join `gateway_decisions` by `execution_id`. The Agent runs page shows sandbox events | 4, 5 | done |
| 010 | Kafka event bus adapter | A Kafka adapter for the EventBus through an optional Redpanda compose profile. The Postgres outbox stays the default | 12 | done |

## Sprint pack rule
- **Feature sprints are vertical slices.** The blueprint first fixes the API contract (typed, under `/v1`, in the OpenAPI snapshot). Then a backend builder brief, a frontend builder brief, and at least one e2e test that runs across both.
- **Infrastructure-only sprints** stay backend only, with at most a small UI touch.
- **Frontend work** follows the project design skill `.claude/skills/governed-design/SKILL.md`.
- **Deployment is parked.** Hosting items wait in `QUESTIONS.md` under "Parked: hosting".

## After the foundation
- Phase 2: gateway layer, built out with OPA, MCP and A2A traffic, approvals and PII guardrails.
- Phase 3: an ask-your-data agent.
- Phase 4: a document agent.

## Program 2: governed data and agent platform (sprints 011 to 032)
The full plan is in `planning/program/` (start with its `README.md`). There are three pillars: Gateway, Data and Agents. The plan is integration first, with an open-source stack, local Compose for development and demos, and cloud through OpenTofu for real deployments. It was condensed from 36 sprints to 22 on 2026-10-11. Milestones:

| Milestone | Sprints | Result | Tag |
|---|---|---|---|
| M0 Foundations | 011–015 | Clean open-source stack, pillars and module boundaries, local or hosted models, reference company, cloud POC lifecycle | `v0.15.0` |
| MG Gateway product | 016–020 | Gateway service and proxy (MCP, LLM API), receipts v2 with anchoring, OPA and replay, guardrails and approvals, SSO, SCIM and delegation | `v0.20.0` |
| MD Data on the client's stack | 021–026 | Read client data in place, connectors and pipelines, products and contracts, grants and query enforcement, lineage and semantic layer, documents, retrieval and grounding | `v0.26.0` |
| MA Agents and insights | 027–029 | Data and integration agents, one agent registry with monitoring and memory, governed dashboards and reports | `v0.29.0` |
| ME Enterprise readiness | 030–032 | Evidence packs and SIEM, resilience and multi-cloud, release and vendor trust | `v1.0.0` |

Sellable point: `v0.20.0`, after Sprint 020. The Gateway and Assurance editions stand on their own.

Freeze point: `v0.27.0`, after Sprint 027. It is a complete first version: a client source row read in place, through to a signed agent answer.

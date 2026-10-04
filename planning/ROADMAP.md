# Roadmap

Milestones only, with no dates. Each sprint is done when its acceptance checks pass.

## Phase 1: polish (independent of the sprints below)
- Keep the hosted instance awake.
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
| 005 | Ports and adapters | Interfaces for the LLM, embeddings, vector store, object store and queue; vectors record their model and dimension; an import-lint rule | 9, 12 | next |
| 006 | Durable jobs and raw storage | A Postgres-backed queue with retries, a dead-letter queue and idempotency keys; ingestion moves to a worker; raw files go to object storage by hash | 6, 11, 13 | planned |
| 007 | Trust baseline | An audit receipts table, an eval regression gate in CI, a cost circuit breaker | 10, 15 | planned |

## After the foundation
- Phase 2: gateway layer, built out with OPA, MCP and A2A traffic, approvals and PII guardrails.
- Phase 3: an ask-your-data agent.
- Phase 4: a document agent.

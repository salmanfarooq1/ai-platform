# Decisions

An index, one line per decision, newest first. The reasoning lives in `docs/adr/` and, for Decisions 1 to 30, in `planning/history/ARCHITECTURE_LOG.md`. This file only points to it. Log entries may carry the date they were recorded.

## Sprint 010: Kafka event bus (ADR-0008)
- **The Postgres outbox stays the default.** `EVENT_BUS=kafka` only changes where the relay publishes. Kafka is never inside a decision transaction.
- **The topic is chosen per event type, and the key is the tenant id.** The relay stops a tenant's batch at its first failure, so that tenant's order holds. Ordering relies on sequential sends.
- **Consumers dedupe by CloudEvent id** in `processed_events`. After `KAFKA_MAX_ATTEMPTS` a message goes to `<topic>.dlq`. The error header holds the exception class only.
- **No migration.** Switching back to `outbox` needs no data change.

## Sprint 009: sandboxed agent execution (ADR-0009)
- **Sprint 009 (2026-10-05):** OpenShell 0.1.2 is the pinned sandbox (Apache-2.0). The sandbox sits behind a `SandboxDriver` port of our own, with the OpenShell SDK driver and a test double. Facts about OpenShell were read from its tagged docs and wheel and checked on a live gateway; none were invented. Rejected: building only against a fake because the project could not be confirmed (it could).
- **Sprint 009:** `AGENT_RUNTIME=openshell` selects the sandbox in the worker. The API still queues the run, so status, the runs API and the sync wait do not change. The default stays `queued` (Q36).
- **Sprint 009:** A run token is bound to one `execution_id` and one principal, carries the boundary the run was accepted with, stores only a hash, lives for the wall limit plus a minute and opens only that run's `/v1/sandbox/runs/{id}/...` routes. Rejected: a short-lived normal API key (it would open every route its scopes allow).
- **Sprint 009:** Tool arguments are checked in the gateway's policy stage against a per-tool JSON Schema, and a call with no stated arguments is checked as `{}`. The deny stores the reason only.
- **Sprint 009:** `sandbox_events` are an observation, not the control record: a failed event write is logged and does not fail the run. The gateway decisions remain the control record and still fail closed.
- **Sprint 009:** The sandbox agent is a thin standard-library program that retrieves and answers through the gateway (Q34).

## Sprint 008: trust baseline (ADR-0012)
- **Sprint 008 (2026-10-05):** Decision records are kept 90 days by default (`DECISION_RETENTION_DAYS`), with a per-tenant override (`identity.py set-retention`). This closes Q7. The number is a placeholder, not a legal period: it is recorded here so it can be changed by setting. Rejected: keeping records forever, and a zero-day minimum (the purge function refuses less than one day).
- **Sprint 008 (QA M2):** Retention has a hard floor of 30 days in the purge function, whatever the caller passes or a tenant stores (`tenants.retention_days` and `DECISION_RETENTION_DAYS` are at least 30; the CLI refuses less). Without the floor a caller could purge its own tenant down to one day. Rejected: trusting the caller's default.
- **Sprint 008 (QA M1, M3):** Purge checkpoints are written only by the purge function, carry a signature of the receipt key, and verification rejects an unsigned one. An unpriced model is costed at the highest known rate; hosted modes refuse to start for a configured model with no price.
- **Sprint 008:** The daily cost cap per tenant defaults to 10 USD (`DAILY_COST_CAP_USD`). A tenant policy may lower it, never raise it. The value is a placeholder (Q26).
- **Sprint 008:** The decision chain is per tenant, takes the next link under an advisory lock, and the receipt signature covers the chain link as well as the decision. Receipts use Ed25519. Rejected: signing each row at write time (a key on the hot path and no way to rotate the signing key without re-signing).
- **Sprint 008:** `/metrics` is unversioned (Prometheus expects it) and open only when `METRICS_PUBLIC=true` (default true in local, false elsewhere); otherwise it needs `admin`.
- **Sprint 008:** The eval gate uses the fake LLM and a fixed suite with deterministic DeepEval metrics, and a tolerance of 0.02 on a stored baseline. The real-provider run is a manual script that needs `REAL_EVAL=1`.

## Sprint 007: durable jobs (ADR-0011)
- **The job queue is Postgres with `FOR UPDATE SKIP LOCKED`, not a broker.** Jobs have leases, retries, a `dead` state and idempotency keys.
- **The default event bus is the transactional outbox.** The default agent runtime is the queued one, so a worker must run.
- **Runs and jobs are visible** only within the caller's allowed knowledge bases. Without `audit:read`, a caller sees only their own runs.
- **Agent usage is booked at most once** per `execution_id`. Run status is durable (Q19 closed).

## Sprint 006: ports and adapters (ADR-0005, ADR-0008, ADR-0009)
- **Only `adapters/` imports provider SDKs.** Composition happens in `adapters/registry.py`.
- **Every chunk records its embedding model and dimension.** Search ignores chunks from another model.
- **Events are CloudEvents 1.0.** A decision row is never lost because of the bus: a failed publish turns an allow into 503 and keeps a deny.
- **Every decision carries the `execution_id`** of the run that caused it.

## Sprint 005b: polish round
- **The name stays descriptive.** Brand names belong to use cases later.
- **The landing page speaks first to the person accountable for the agents.** Engineers come second. Headline: "Your agents can only ever do less." Subline: "Control what your agents can do. See everything they did."
- **The hero is the real product:** a receipt and a denied call, using console components with example data. The WebGL ring is optional.
- **Mechanism detail moves to a How it works page.** The landing page keeps one line per capability, and there is no problem section.
- **Ink and paper.** Warm neutrals and ink, verdicts as the only strong color, one petrol seal color. The brand blue is removed.
- **005b is its own sprint**, between 005 and 006.
- **No screenshot review round.** The design rules and QA are the quality gate.

## Direction after Sprint 004
- **The frontend is first-class.** It is designed and built with the backend. Feature sprints are vertical slices: the API contract comes first, then backend and frontend briefs and one e2e test across both. `ROADMAP.md`.
- **New sprint order:** 005 frontend foundation and showcase, 006 ports and adapters with EventBus and AgentRuntime, 007 durable jobs with an outbox, 008 trust with metrics and decision retention, 009 OpenShell sandbox, 010 Kafka adapter. `ROADMAP.md`.
- **Deployment is parked.** Hosting items wait in `QUESTIONS.md`.
- **One project design skill.** `.claude/skills/governed-design/` merges apple-design, the MIT taste skill (main, soft and minimalist) and `docs/UI_GUIDELINES.md`.
- **Web edge inside the monolith, not a separate BFF.** ADR-0007 (Sprint 005). Planned ADRs: 0008 event bus, 0009 agent runtime.

## Sprint 004: gateway core
- **One `enforce()` for every model, tool and KB call.** Any error is a deny. Decision 26, ADR-0006.
- **Decision writes fail closed.** A failed write on an allow gives 503 `decision_unrecorded`. Token booking after the work stays best effort. Decision 26, ADR-0006.
- **Rate limit and token budget are gateway stages, not middleware.** Same Redis keys and 429 codes. Redis down gives 503 `dependency_unavailable`. Decisions 12 and 15 are superseded. Decision 26, ADR-0006.
- **No policy row means the platform default (what scopes grant). A policy can only narrow.** Decision 26, ADR-0006.
- **Unknown KB under a KB allowlist is 403, not 404.** Accepted, noted in ADR-0006.

## Sprint 003: identity and tenancy
- **Tenant comes only from a verified API key or JWT. Row-level security isolates tenants.** Decision 25, ADR-0003.
- **The app connects as `gap_app`, a role without superuser or `BYPASSRLS`. Migrations and the admin CLI use the owner role.** Decision 25.
- **Bulk ingest uses a pipelined INSERT instead of `COPY`, because Postgres refuses `COPY FROM` into a table with row-level security.** Decision 25.
- **Namespaces become knowledge bases checked against the caller's tenant.** Decision 25.

## Sprint 002: platform base
- **Validated settings, Alembic, `/v1`, one error format, JSON logs and traces.** Decision 24.
- **Lint is clean on `main` (Q3 closed).** `test_llm.py` was rewritten against `generate_with_citations` (B1 closed), and the configured models have pricing entries (B2 closed). See `CHANGELOG.md`.

## Sprint 001: foundation architecture
- **Modular monolith.** ADR-0001.
- **Postgres is the source of truth.** ADR-0002.
- **Tenancy with `tenant_id` and row-level security.** ADR-0003.
- **Governance outside the agent, behind one `enforce()`.** ADR-0004.
- **Ports and adapters for external providers.** ADR-0005.

## Sprint 000: operating structure
- **Sprint 000:** The hosted mode is renamed from `demo` to `public-preview`, and an unknown `MODE` fails at startup. Rejected: keeping `demo` as an alias.
- **Sprint 000:** The platform has no brand name. It is the "Governed Agent Platform". `BRANDING.md` becomes `docs/UI_GUIDELINES.md`.
- **Sprint 000:** One `.env*` ignore pattern (`.env`, `.env.*`, `!.env.example`) instead of one line per file.
- **Sprint 000:** Working method: planning and review run through files, with the roles Architect, Builder and QA. One branch per sprint, and no model commits.
- **Sprint 000:** Cost stays at free tiers. Any paid dependency is a stop condition.

## Before Sprint 000
- **Decisions 1–23:** labs, retrieval, caching, the agent, MCP, cost tracking and the free-tier deploy. See `planning/history/ARCHITECTURE_LOG.md`.

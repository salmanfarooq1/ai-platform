# Decisions

An index, one line per decision, newest first. The reasoning lives in `docs/ARCHITECTURE.md` (Decision N) and `docs/adr/`. This file only points to it. Log entries may carry the date they were recorded.

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
- **Decisions 1–23:** labs, retrieval, caching, the agent, MCP, cost tracking and the free-tier deploy. See `docs/ARCHITECTURE.md`.

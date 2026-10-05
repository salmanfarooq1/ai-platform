# State

Snapshot only. Edit in place and keep it under 60 lines.

## Now
- **Sprints 000 to 006:** done and QA signed off (see `ROADMAP.md`, `CHANGELOG.md`). Sprints 000 to 004 are on `main`. The commit blocks for 005 onward are in `planning/COMMIT_PLAN.md`, and a human runs them.
- **Sprint 005 and 005b:** the web-edge session (ADR-0007), the console API (decisions, requests, overview, reason codes), and the TypeScript UI with the ink-and-paper design system (ADR-0010, `docs/design/`).
- **Sprint 006:** typed ports and adapters with contract suites, embedding provenance (migration `0007`), the CloudEvents bus (ADR-0008) and the agent runtime with an `execution_id` on every decision (ADR-0009).
- **Tests:** 1097 backend (10 live-MinIO skipped), 167 Vitest and 71 Playwright.

## Next
- **Sprint 007 (durable jobs and the outbox):** next. Then 008 trust, 009 sandboxed agents, 010 Kafka adapter. Each pack has its blueprint and builder brief.
- **Direction:** feature sprints are vertical slices. The contract comes first, then the backend, then the UI, with one e2e test across both. See `ROADMAP.md`.
- **Design:** every frontend builder follows `.claude/skills/governed-design/SKILL.md`.
- **Deployment is parked.** All hosting items wait in `QUESTIONS.md` under "Parked: hosting".

## Platform today
- **AI layer:** hybrid retrieval (BM25 + pgvector + RRF, optional cross-encoder), a LangGraph agent with a verify loop, an MCP server. Providers sit behind ports (`ports/`, `adapters/`, composition root `adapters/registry.py`); only `adapters/` imports a provider SDK (import-lint test).
- **Data:** streaming ingestion with content-hash change detection. Every chunk records its embedding model and dimension; search ignores chunks of another model and `/v1/health` counts them (`stale_vectors`). The object store port exists (local and S3 adapters) but nothing calls it yet; no document versions.
- **Trust:** FinOps middleware, the token budget as a gateway stage, a `usage_log` table, a DeepEval harness in `scripts/`. JSON logs with request and trace ids, OpenTelemetry FastAPI spans, one error format.
- **Identity and tenancy:** every `/v1` route except `/v1/health` needs a bearer API key or JWT; the tenant comes only from the credential. Postgres row-level security isolates tenants, caches and limits key on identity, and the app refuses to run as a superuser or `BYPASSRLS` role (it connects as `gap_app`; Alembic and `scripts/admin/identity.py` use the owner role).
- **Gateway:** `enforce()` runs principal, boundary, policy, input guardrails, rate and budget; any error is a deny. The agent and MCP tools only act through it. Tenant policies (`set-policy`) narrow KBs, tools, models, tool-call and token limits; with none, scopes grant against the platform defaults. Every call writes a `gateway_decisions` row (SHA-256 of the input, no text); the write fails closed: a failed write on an allow gives 503 `decision_unrecorded`. Booking tokens after the work stays best effort.
- **Platform base:** validated settings, Alembic migrations (`0001` baseline, `0002` to `0007` since), all product routes under `/v1` (`/` and `/health` unversioned), mypy and ruff clean, CI with lint, mypy, unit, integration+e2e and a migration check.
- **Hosting:** Render free tier, `MODE=public-preview`, Neon Postgres.

## Known gaps
These are the 11 gaps listed in `docs/architecture/FOUNDATION.md`; gap 1 (no identity) is closed by Sprint 003 and gap 9 (the agent can call any tool) by Sprint 004. The accepted Sprint 004 lows are in `RISKS.md`. The top ones left:
- Ingestion runs inside the request.
- Stale vectors are ignored, not re-embedded, and agent run status lives in memory: both wait for the queue (Sprint 007).
- `gateway_decisions` has no retention yet (Q7). Decision writes fail closed, and Sprint 007 extends the table.
- Chunks ingested before Sprint 002 have no `source_filename` in metadata, so they still cite `unknown` until re-ingested.

## Blockers
- None for local work. The hosting items (Q2, Q6, B9, Q8 rollout) are parked. Sprint 006 open items are Q16 to Q20 in `QUESTIONS.md`; the live MinIO run is not verified here (B12).
- Q8: nobody has yet written the first real tenant policies. Until then the platform default applies.

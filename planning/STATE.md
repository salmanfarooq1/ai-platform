# State

Snapshot only. Edit in place and keep it under 60 lines.

## Now
- **Sprints 000 to 007:** done and QA signed off (see `ROADMAP.md`, `CHANGELOG.md`). Sprints 000 to 004 are on `main`. The commit blocks for 005 onward are in `planning/COMMIT_PLAN.md`, and a human runs them.
- **Sprint 005 and 005b:** the web-edge session (ADR-0007), the console API (decisions, requests, overview, reason codes), and the TypeScript UI with the ink-and-paper design system (ADR-0010, `docs/design/`).
- **Sprint 006:** typed ports and adapters with contract suites, embedding provenance (migration `0007`), the CloudEvents bus (ADR-0008) and the agent runtime with an `execution_id` on every decision (ADR-0009).
- **Sprint 007:** durable jobs on Postgres (migration `0008`), workers (`python -m workers`), the transactional outbox, raw files stored by SHA-256, ingestion and agent runs as jobs, the Library shows job progress (ADR-0011, ADR-0008 outbox section). Runs and jobs are visible only within the caller's allowed knowledge bases.
- **Tests:** 1188 backend (10 live-MinIO skipped), 182 Vitest and 72 Playwright.

## Next
- **Sprint 008 trust**, then 009 sandboxed agents and 010 Kafka adapter. Each pack has its blueprint and builder brief. Sprint 008 also owns retention of the new tables (Q21).
- **Direction:** feature sprints are vertical slices. The contract comes first, then the backend, then the UI, with one e2e test across both. See `ROADMAP.md`.
- **Design:** every frontend builder follows `.claude/skills/governed-design/SKILL.md`.
- **Deployment is parked.** All hosting items wait in `QUESTIONS.md` under "Parked: hosting".

## Platform today
- **AI layer:** hybrid retrieval (BM25 + pgvector + RRF, optional cross-encoder), a LangGraph agent with a verify loop, an MCP server. Providers sit behind ports (`ports/`, `adapters/`, composition root `adapters/registry.py`); only `adapters/` imports a provider SDK (import-lint test).
- **Data:** streaming ingestion with content-hash change detection. Every chunk records its embedding model and dimension; search ignores chunks of another model and `/v1/health` counts them (`stale_vectors`). Every upload is stored raw in the object store by SHA-256 (local and S3 adapters); no document versions.
- **Trust:** FinOps middleware, the token budget as a gateway stage, a `usage_log` table, a DeepEval harness in `scripts/`. JSON logs with request and trace ids, OpenTelemetry FastAPI spans, one error format.
- **Identity and tenancy:** every `/v1` route except `/v1/health` needs a bearer API key or JWT; the tenant comes only from the credential. Postgres row-level security isolates tenants, caches and limits key on identity, and the app refuses to run as a superuser or `BYPASSRLS` role (it connects as `gap_app`; Alembic and `scripts/admin/identity.py` use the owner role).
- **Gateway:** `enforce()` runs principal, boundary, policy, input guardrails, rate and budget; any error is a deny. The agent and MCP tools only act through it. Tenant policies (`set-policy`) narrow KBs, tools, models, tool-call and token limits; with none, scopes grant against the platform defaults. Every call writes a `gateway_decisions` row (SHA-256 of the input, no text); the write fails closed: a failed write on an allow gives 503 `decision_unrecorded`. Booking tokens after the work stays best effort.
- **Platform base:** validated settings, Alembic migrations (`0001` baseline, `0002` to `0008` since), all product routes under `/v1` (`/` and `/health` unversioned), mypy and ruff clean, CI with lint, mypy, unit, integration+e2e and a migration check.
- **Hosting:** Render free tier, `MODE=public-preview`, Neon Postgres.

## Known gaps
These are the 11 gaps listed in `docs/architecture/FOUNDATION.md`; gap 1 (no identity) is closed by Sprint 003 and gap 9 (the agent can call any tool) by Sprint 004. The accepted Sprint 004 lows are in `RISKS.md`. The top ones left:
- A worker must run for ingestion and agent runs (`docker compose up -d worker`, `python -m workers`, or `EMBEDDED_WORKERS=1`). Hosting the worker is parked (Q23).
- Stale vectors are ignored, not re-embedded (the queue exists now; no re-embedding job is scheduled). Agent run status is durable (Q19 closed).
- `gateway_decisions` has no retention yet (Q7). Decision writes fail closed. `jobs`, `outbox` and `processed_events` have no retention either (Q21).
- Chunks ingested before Sprint 002 have no `source_filename` in metadata, so they still cite `unknown` until re-ingested.

## Blockers
- None for local work. The hosting items (Q2, Q6, B9, Q8 rollout) are parked. Open items from Sprints 006 and 007 are Q16 to Q25 in `QUESTIONS.md`; the live MinIO run is not verified here (B12).
- Q8: nobody has yet written the first real tenant policies. Until then the platform default applies.

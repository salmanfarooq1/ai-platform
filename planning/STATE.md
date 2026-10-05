# State

Snapshot only. Edit in place and keep it under 60 lines.

## Now
- **Sprints 000 to 005b:** done, QA signed off (see `ROADMAP.md`, `CHANGELOG.md`). Commits are proposed in each sprint's `report.md` for the branches `sprint/NNN-slug`; a human runs them.
- **Sprint 004 (gateway core):** `gateway.enforce()` for every model, tool and KB call, the immutable `ExecutionBoundary`, tenant policies (migration `0005`), the `gateway_decisions` record, rate limit and budget as gateway stages, all failing closed. QA follow-ups M1 to M4, L1 to L4 and N1 fixed. 709 tests pass (unit 424, integration and e2e 285, 0 skipped). See `planning/sprints/004-gateway-core/report.md` and ADR-0006.
- **Sprint 005 (frontend foundation and showcase):** the web-edge cookie session (ADR-0007, migration `0006`), read-only console endpoints under `audit:read`, the new TypeScript UI (workspace, governance console and landing page), and the project design skill. 805 backend tests, 34 Vitest and 36 Playwright tests pass. See `planning/sprints/005-frontend-foundation/report.md`.

## Next
- **Direction:** the frontend is first-class and is designed and built together with the backend. Feature sprints are vertical slices (contract first, backend brief, frontend brief, one e2e across both). See the pack rule in `ROADMAP.md`.
- **Sprint 005b (polish round):** done. Ink-and-paper tokens, the new landing page and How it works page, Overview, Requests with a drawer, plain reasons, a governance line, the walkthrough, Cmd+K, and `docs/design/`. 875 backend tests, 162 Vitest tests and 70 Playwright tests pass.
- **Sprint 006 (ports and adapters, EventBus, AgentRuntime):** next, with its pack in `planning/sprints/006-ports-adapters/`. Then 007 durable jobs, 008 trust, 009 sandboxed agents, 010 Kafka adapter.
- **Design:** every frontend builder follows `.claude/skills/governed-design/SKILL.md`.
- **Deployment is parked.** All hosting items wait in `QUESTIONS.md` under "Parked: hosting".

## Platform today
- **AI layer:** hybrid retrieval (BM25 + pgvector + RRF, optional cross-encoder), a LangGraph agent with a verify loop, an MCP server.
- **Data:** streaming ingestion with content-hash change detection. No raw-file store and no document versions.
- **Trust:** FinOps middleware, the token budget as a gateway stage, a `usage_log` table, a DeepEval harness in `scripts/`. JSON logs with request and trace ids, OpenTelemetry FastAPI spans, one error format.
- **Identity and tenancy:** every `/v1` route except `/v1/health` needs a bearer API key or JWT; the tenant comes only from the credential. Postgres row-level security isolates tenants, caches and limits key on identity, and the app refuses to run as a superuser or `BYPASSRLS` role (it connects as `gap_app`; Alembic and `scripts/admin/identity.py` use the owner role).
- **Gateway:** `enforce()` runs principal, boundary, policy, input guardrails, rate and budget; any error is a deny. The agent and MCP tools only act through it. Tenant policies (`set-policy`) narrow KBs, tools, models, tool-call and token limits; with none, scopes grant against the platform defaults. Every call writes a `gateway_decisions` row (SHA-256 of the input, no text); the write fails closed: a failed write on an allow gives 503 `decision_unrecorded`. Booking tokens after the work stays best effort.
- **Platform base:** validated settings, Alembic migrations (`0001` baseline, `0002` to `0005` since), all product routes under `/v1` (`/` and `/health` unversioned), mypy and ruff clean, CI with lint, mypy, unit, integration+e2e and a migration check.
- **Hosting:** Render free tier, `MODE=public-preview`, Neon Postgres.

## Known gaps
These are the 11 gaps listed in `docs/architecture/FOUNDATION.md`; gap 1 (no identity) is closed by Sprint 003 and gap 9 (the agent can call any tool) by Sprint 004. The accepted Sprint 004 lows are in `RISKS.md`. The top ones left:
- Ingestion runs inside the request.
- `gateway_decisions` has no retention yet (Q7). Decision writes fail closed, and Sprint 007 extends the table.
- Chunks ingested before Sprint 002 have no `source_filename` in metadata, so they still cite `unknown` until re-ingested.

## Blockers
- None for local work. The hosting items (Q2, Q6, B9, Q8 rollout) are parked.
- Q8: nobody has yet written the first real tenant policies. Until then the platform default applies.

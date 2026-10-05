# State

Snapshot only. Edit in place and keep it under 60 lines.

## Now
- **Sprints 000 to 010:** done and QA signed off (see `ROADMAP.md`, `CHANGELOG.md`). Sprints 000 to 004 are on `main`. The commit blocks for 005 onward are in `planning/COMMIT_PLAN.md`, and a human runs them.
- **Sprint 005 and 005b:** the web-edge session (ADR-0007), the console API (decisions, requests, overview, reason codes), and the TypeScript UI with the ink-and-paper design system (ADR-0010, `docs/design/`).
- **Sprint 006:** typed ports and adapters with contract suites, embedding provenance (migration `0007`), the CloudEvents bus (ADR-0008) and the agent runtime with an `execution_id` on every decision (ADR-0009).
- **Sprint 007:** durable jobs on Postgres (migration `0008`), workers (`python -m workers`), the transactional outbox, raw files stored by SHA-256, ingestion and agent runs as jobs, the Library shows job progress (ADR-0011, ADR-0008 outbox section). Runs and jobs are visible only within the caller's allowed knowledge bases.
- **Sprint 008:** signed receipts and a per-tenant hash chain (migration `0009`, ADR-0012), retention and purge of decisions (90 days default, Q7 closed), the eval gate in CI, a daily cost cap stage, `/metrics` with an optional Prometheus and Grafana profile, and the Trust page. Report: `planning/sprints/008-trust-baseline/report.md`.
- **Sprint 009:** `AGENT_RUNTIME=openshell` runs each agent run in an OpenShell 0.1.2 sandbox behind a `SandboxDriver` port (ADR-0009, `docs/runbooks/openshell.md`). Run tokens bound to one run, `tool_arguments` policy schemas (`tool_argument_not_allowed`), `sandbox_events` (migration `0010`) merged with decisions in the runs API and on the Agent runs page. Run live here on one setup (`scripts/verify/openshell.sh`); the standard images, other drivers and hosts are not verified. Report: `planning/sprints/009-sandboxed-agents/report.md`.
- **Sprint 010:** `EVENT_BUS=kafka` makes the outbox relay publish to Kafka (`aiokafka` 0.14.0, topic per event type, key = tenant id, CloudEvents binary mode), with consumer-group dedupe and `<topic>.dlq` (ADR-0008, `docs/runbooks/kafka.md`). Compose profile `kafka` (Redpanda v24.2.7). No migration, and `outbox` is still the default. Run live here on one node (`scripts/verify/kafka.sh`); SASL, TLS, several brokers and several consumers are not verified. Awaiting QA. Report: `planning/sprints/010-kafka-event-bus/report.md`.
- **Tests:** 1568 backend (10 live-MinIO skipped), 207 Vitest and 82 Playwright.

## Next
- **The planned roadmap (000 to 010) is complete.** The next pack is not yet written. Open items are listed in `QUESTIONS.md`. Retention of `jobs`, `outbox`, `processed_events` and raw files is still open (Q27). No consumer uses Kafka yet (Q41).
- **Direction:** feature sprints are vertical slices. The contract comes first, then the backend, then the UI, with one e2e test across both. See `ROADMAP.md`.
- **Design:** every frontend builder follows `.claude/skills/governed-design/SKILL.md`.
- **Deployment is parked.** All hosting items wait in `QUESTIONS.md` under "Parked: hosting".

## Platform today
- **AI layer:** hybrid retrieval (BM25 + pgvector + RRF, optional cross-encoder), a LangGraph agent with a verify loop, an MCP server. Providers sit behind ports (`ports/`, `adapters/`, composition root `adapters/registry.py`); only `adapters/` imports a provider SDK (import-lint test).
- **Data:** streaming ingestion with content-hash change detection. Every chunk records its embedding model and dimension; search ignores chunks of another model and `/v1/health` counts them (`stale_vectors`). Every upload is stored raw in the object store by SHA-256 (local and S3 adapters); no document versions.
- **Trust:** FinOps middleware, the token budget as a gateway stage, a `usage_log` table, signed receipts on a per-tenant hash chain, a daily cost cap, an eval gate in CI, `/metrics`. JSON logs with request and trace ids, OpenTelemetry FastAPI spans, one error format.
- **Identity and tenancy:** every `/v1` route except `/v1/health` needs a bearer API key or JWT; the tenant comes only from the credential. Postgres row-level security isolates tenants, caches and limits key on identity, and the app refuses to run as a superuser or `BYPASSRLS` role (it connects as `gap_app`; Alembic and `scripts/admin/identity.py` use the owner role).
- **Gateway:** `enforce()` runs principal, boundary, policy, input guardrails, rate and budget; any error is a deny. The agent and MCP tools only act through it. Tenant policies (`set-policy`) narrow KBs, tools, models, tool-call and token limits; with none, scopes grant against the platform defaults. Every call writes a `gateway_decisions` row (SHA-256 of the input, no text); the write fails closed: a failed write on an allow gives 503 `decision_unrecorded`. Booking tokens after the work stays best effort.
- **Platform base:** validated settings, Alembic migrations (`0001` baseline, `0002` to `0010` since; Sprint 010 adds none), all product routes under `/v1` (`/` and `/health` unversioned), mypy and ruff clean, CI with lint, mypy, unit, integration+e2e and a migration check.
- **Hosting:** Render free tier, `MODE=public-preview`, Neon Postgres.

## Known gaps
These are the 11 gaps listed in `docs/architecture/FOUNDATION.md`; gap 1 (no identity) is closed by Sprint 003 and gap 9 (the agent can call any tool) by Sprint 004. The accepted Sprint 004 lows are in `RISKS.md`. The top ones left:
- A worker must run for ingestion and agent runs (`docker compose up -d worker`, `python -m workers`, or `EMBEDDED_WORKERS=1`). Hosting the worker is parked (Q23).
- Stale vectors are ignored, not re-embedded (the queue exists now; no re-embedding job is scheduled). Agent run status is durable (Q19 closed).
- Decision records are purged after 90 days (Q7 closed). `jobs`, `outbox`, `processed_events` and raw files have no retention yet (Q27). The decision chain is not anchored outside Postgres (Q29).
- Sandboxed runs need an OpenShell gateway, Docker and an image on the worker host (Q38). The agent in the sandbox is a thin retrieve-and-answer program (Q34). OpenShell logs no event for a refused file read (Q37). `sandbox_events` and `run_tokens` have no retention (Q35).
- Chunks ingested before Sprint 002 have no `source_filename` in metadata, so they still cite `unknown` until re-ingested.

## Blockers
- None for local work. The hosting items (Q2, Q6, B9, Q8 rollout) are parked. Open items from Sprints 006 to 010 are Q16 to Q46 in `QUESTIONS.md`; the live MinIO run is not verified here (B12), and the OpenShell run used locally rebuilt images (B14).
- Q8: nobody has yet written the first real tenant policies. Until then the platform default applies.

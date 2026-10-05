# Changelog

All notable changes, newest first, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. The detailed build history is in `planning/history/`.

## [Unreleased]

### Added
- **Console and workspace.** A React and TypeScript UI with these screens:
  - Console: Overview, Requests (with a detail drawer), Decisions, Policies, Keys, Usage, Agent runs, Trust and System.
  - Workspace: Ask, Library and History.
  - A guided walkthrough, a command palette, and public Landing and How it works pages.
  - Design tokens in the W3C format, with drift, color and contrast checks.
- **Web edge session.** Cookie sign-in with CSRF protection, and an optional read-only preview session.
- **Console API.** Decisions, requests, overview, policies, principals, usage summary and the reason catalogue, all under `audit:read`.
- **Ports and adapters.** A typed interface for every provider and a registry that builds them from settings. Embedding provenance on every chunk, a stale-vector count, and an ordered embedding fallback.
- **Events.** CloudEvents through a transactional outbox, with a relay to in-process subscribers or Kafka. Consumers dedupe by event id. Kafka adds consumer groups and dead-letter topics.
- **Durable jobs.** A Postgres job queue with leases, retries, dead jobs and idempotency keys. Ingestion and agent runs run in workers (`python -m workers`). Raw files are stored once by SHA-256 in local or S3 storage.
- **Trust.**
  - Decision records chained per tenant and signed as Ed25519 receipts, with an offline verifier.
  - Decision retention, 90 days by default with a 30-day floor, purged with signed checkpoints.
  - A daily cost cap stage.
  - Prometheus metrics, with an optional Prometheus and Grafana profile.
  - An eval regression gate in CI.
- **Sandboxed agent runs.**
  - `AGENT_RUNTIME=openshell` runs each agent run in an OpenShell sandbox. The sandbox's only route is the platform, it writes only its work directory, and it runs under limits.
  - Each run gets a run token bound to it.
  - Policies can check tool arguments against JSON Schemas.
  - Sandbox events appear on the run timeline.
- **Documentation** in one standard set: getting started, architecture, configuration, deployment, operations, API, contracts and security. Reference tables are generated from the code.

### Changed
- `POST /v1/ingest` answers `202` with a job instead of the ingest result. `POST /v1/agent/query` may answer `202` with an `execution_id`.
- A worker must run for ingestion and agent runs. Use `python -m workers`, the compose `worker` service, or `EMBEDDED_WORKERS=1`.
- `RECEIPT_SIGNING_KEY` is required outside `local` mode. The API and workers must share it.
- In hosted modes, every configured model must have a price, or the process refuses to start.
- The OpenAPI snapshot moved to `docs/api/openapi.json`.

### Security
- Job and run routes show only the knowledge bases the caller may read. Without `audit:read`, a caller sees only its own runs.
- Error responses, job errors, event headers and logs never carry exception text, input text or secrets.

## [0.4.0]

### Added
- **Platform base.** Validated settings, Alembic migrations, `/v1` routes, one error format, JSON logs with request and trace ids, OpenTelemetry tracing, type checks and CI.
- **Identity and tenancy.** API keys and JWT, scopes, tenants, knowledge bases, Postgres row-level security, the `gap_app` app role, and the admin CLI.
- **Gateway.** `enforce()` on every model, tool and knowledge-base call, with principal, boundary, policy, guardrails, rate and budget stages. Versioned tenant policies. A decision record for every call, written fail closed.

### Changed
- The hosted mode is named `public-preview`. An unknown `MODE` stops the process at start.
- Every product route needs a credential, except `/v1/health`.

Earlier work (memory-efficient ingestion, async HTTP, pgvector, hybrid retrieval, caching, the agent, MCP and the first deployment) is described in `planning/history/BUILD_HISTORY.md`.

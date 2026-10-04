# Sprint 002: Platform base — Requirements

## Goal
Give the platform a production base: validated config, versioned schema migrations, a versioned API with one error format, structured logs and traces, a type check, a clean lint, and a real integration + end-to-end test harness that runs against real Postgres and Redis.

## Why it matters
Every later sprint (identity, gateway, adapters, jobs) changes schema, API and config. Without migrations, `/v1`, validated settings and a real E2E harness, each of those changes is unsafe and unprovable.

## Scope
1. **Settings:** `pydantic-settings` `Settings` class; fail fast at startup on bad or missing values. `config.py` keeps its public names (built from `Settings`) so callers don't change.
2. **Migrations:** Alembic (async-free, SQL-first). Baseline migration `0001` reproduces `core/database/schema.sql` idempotently, so it is safe on the hosted DB that already has the tables. `schema.sql` is deleted; Docker and local setup run `alembic upgrade head`.
3. **API versioning:** every product route under `/v1`. Root `/` and `/health` stay unversioned for the platform health check; `/v1/health` also exists. MCP moves to `/v1/mcp/...`. UI and `claude_desktop_config.json` updated in lockstep.
4. **One error format** for all errors: `{"error": {"code": str, "message": str, "request_id": str}}`. Covers HTTPException, validation errors, rate limit, token budget, guardrail blocks, and unhandled exceptions (500, no stack trace in the body).
5. **Observability:** JSON logs (one object per line) carrying `request_id` and `trace_id`. OpenTelemetry SDK with FastAPI instrumentation; OTLP exporter only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, otherwise no exporter. Every response carries `X-Request-ID` and `X-Trace-ID`.
6. **Type check:** mypy configured in `pyproject.toml`, passing on `api/ core/ config.py`.
7. **Lint:** `ruff check api/ core/ tests/` clean (33 errors today).
8. **Pre-existing failures:** B1 (`tests/unit/test_llm.py` imports a function removed on purpose in commit efde99f — rewrite the test against the current `api/services/llm.py`, do not delete coverage); B2 (missing `MODEL_PRICING` entry for the model the tests expect — check which model the config uses and fix the right side).
9. **Test harness:** real integration and E2E tiers replacing the placeholders. Real Postgres (pgvector) and Redis Stack; fake LLM and embeddings only.
10. **CI:** jobs for lint, mypy, unit, and integration+E2E (with `pgvector/pgvector:pg16` and `redis/redis-stack-server` service containers), plus a migration check.

## Out of scope
Auth, tenancy, the gateway, provider interfaces, queues (Sprints 003–006). UI redesign. Changing retrieval or agent behaviour.

## Rules that apply
Strict rules 7, 8, 10 (trace part), 14, 15. Working agreements in `AGENTS.md`. Cost stays $0.

## Edge cases
- Hosted DB already has every table: migration 0001 must be a no-op on it except recording the Alembic version.
- `MODE=public-preview` or `prod` without `DATABASE_URL` must fail at startup (no placeholder DSNs).
- Render free tier is 512MB: OpenTelemetry must not add an exporter or background thread unless configured.

## Open questions
Q4 (Neon backup before first migration) — the migration is non-destructive, so it is not blocking.

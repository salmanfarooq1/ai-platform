# Sprint 002: Platform base — Blueprint

## Files to read first
`AGENTS.md`, `docs/architecture/FOUNDATION.md`, `config.py`, `api/main.py`, `core/database/pool.py`, `core/database/schema.sql`, `api/middleware/*.py`, `api/routers/*.py`, `api/mcp/transport.py`, `api/services/llm.py`, `core/clients/embeddings.py`, `api/agent/graph.py`, `tests/conftest.py`, `.github/workflows/tests.yml`, `Dockerfile`, `ui/src/api/client.js`, `ui/src/api/ingest.js`.

## Files to create
| Path | Purpose |
|---|---|
| `core/settings.py` | `Settings(BaseSettings)`; `get_settings()` cached |
| `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_baseline.py` | Migrations; DSN from `Settings`; baseline = current schema, idempotent (`IF NOT EXISTS`) |
| `api/errors.py` | `ErrorBody` model, exception handlers, `error_response(code, message, status)` helper used by middleware |
| `api/observability.py` | JSON log formatter, `setup_logging()`, `setup_tracing(app)` |
| `tests/fakes.py` | Deterministic fake LLM + fake embeddings |
| `tests/integration/conftest.py`, `tests/e2e/conftest.py` | Real DB/Redis fixtures (replace placeholders) |
| `tests/integration/test_*.py`, `tests/e2e/test_*.py` | See test plan |

## Files to modify
`config.py` (build dicts from `Settings`, keep names), `api/main.py` (`/v1` router prefix, handlers, logging, tracing), all middleware that returns its own JSON (use `error_response`), `api/mcp/transport.py` (paths), `core/database/pool.py`, `Dockerfile` (copy `alembic.ini` + `migrations/`, run `alembic upgrade head` before uvicorn), `docker-compose.yml` if it mounts `schema.sql`, `pyproject.toml` (deps, mypy, markers), `.github/workflows/tests.yml`, `ui/src/api/client.js` + `ingest.js` (prefix `/v1`), `claude_desktop_config.json`, `README.md`, `AGENTS.md` (commands), `docs/ARCHITECTURE.md` (API + data sections), `CHANGELOG.md`, `planning/STATE.md`. Delete `core/database/schema.sql` and the two placeholder test files.

## Steps
1. Baseline: run unit tests and ruff, save output to `evidence/baseline-*.txt`.
2. Fix lint (ruff) and B1/B2.
3. Settings: required in `public-preview`/`prod`: `DATABASE_URL`, `REDIS_URL`. Remove placeholder DSNs. Keep local defaults. Unit tests for fail-fast.
4. Alembic baseline. Verify on an empty DB, and on a DB pre-loaded from the old `schema.sql` (simulates hosted Neon): both reach head, the second with no table changes.
5. `/v1` + error handlers + middleware error bodies.
6. JSON logging + OTel + `X-Trace-ID`.
7. mypy config; fix errors. A per-module `ignore_errors` is allowed only for third-party-shaped code and must be listed in `report.md` with the reason.
8. Test harness + tests (below). 9. CI. 10. UI path change + `npm run build`. 11. Docs.

## Data / API changes
- Data: none beyond the `alembic_version` table.
- API: all product routes move from `/x` to `/v1/x`. Old paths return 404 in the standard error format. `/` and `/health` unchanged.

## Test plan
**Fakes (`tests/fakes.py`):**
- Embeddings: hash each lower-cased word into one of 768 buckets, sum, L2-normalise. Same text → same vector; shared words → higher cosine.
- LLM: patch `litellm.acompletion` (and whatever `ChatLiteLLM` calls) with a fake that answers from the context it was given, citing the first chunk, and records every call. For the agent, the fake first returns a `retrieve` tool call, then a final answer. Never touch the network: a test fixture must make any real `litellm` network call raise.

**Fixtures:** session fixture creates a fresh DB `gap_test_<random>` on the local Postgres, runs `alembic upgrade head`, drops it at the end. Redis: use DB index 15 and `FLUSHDB` between tests. Start the app with its real lifespan (`asgi-lifespan` `LifespanManager` + `httpx.AsyncClient(ASGITransport)`). If Postgres or Redis is unreachable, skip the tier with a clear reason — never pass silently.

**Integration tests (real DB, no HTTP):** migrations (empty DB → head; old-schema DB → head no-op; `alembic downgrade` not required); ingestion lifecycle (new / unchanged / updated changes rows correctly); hybrid retrieval returns the ingested chunk for a matching query and respects namespace; usage_log write; feedback write.

**E2E tests (HTTP through the real app):**
1. Ingest a markdown file → `/v1/search` returns an answer citing that file → `/v1/documents` lists it → `/v1/feedback` accepted → `/v1/analytics` reflects the usage row.
2. Re-ingest same file → "unchanged"; changed file → "updated", old chunks gone.
3. `/v1/agent/query` runs the graph with the fake LLM: tool call happens, answer cites the doc.
4. Error format: 404 unknown route, 422 bad body, guardrail block, rate limit (lower the limit via settings in the test), unhandled exception (inject a failing route in test app) → all match `{"error": {...}}`, no stack trace.
5. Every response has `X-Request-ID` and `X-Trace-ID`; a log line for the request is valid JSON containing both.
6. Old unversioned path (e.g. `/search`) → 404.
7. MCP: `/v1/mcp/sse` connects (or the MCP tools list via the in-process server).

Assertions check real values (row counts, returned citations, header formats), not just status codes.

## Walking-skeleton notes
- OTel: SDK + FastAPI spans only. Deferred: DB/Redis/LLM spans (Sprint 005 adapters are the seam). Cost bounded: no exporter unless configured.
- Migrations: forward only. Deferred: schema-drift autogenerate check (needs SQLAlchemy models; seam = `migrations/env.py` `target_metadata`).
- mypy: non-strict across the codebase; strict for new modules (`core/settings.py`, `api/errors.py`, `api/observability.py`).

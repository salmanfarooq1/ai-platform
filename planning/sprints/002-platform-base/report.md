# Sprint 002: Platform base. Builder report

## 1. Acceptance
| Check | Status | Evidence |
|---|---|---|
| A1 ruff 0 errors | done | `evidence/ruff.txt` |
| A2 mypy success | done | `evidence/mypy.txt` (57 files, no `ignore_errors`) |
| A3 unit 0 failed, 0 errors | done | `evidence/pytest-unit.txt` |
| A4 int+e2e 0 failed, 0 skipped | done | `evidence/pytest-int-e2e.txt` |
| A5 Postgres stopped gives skips with reason | done | `evidence/pytest-skip.txt` (66 skipped, 0 passed, 0 errors, reason on every skip) |
| A6 migrate fresh and existing DB | done | `evidence/migrate-fresh.txt`, `evidence/migrate-existing.txt` (`\d+` before and after IDENTICAL) |
| A7 fail-fast settings | done | `evidence/settings-failfast.txt` |
| A8 live run, curl, JSON logs | done | `evidence/live-curl.txt`, `evidence/live-log.txt` (26 lines, all valid JSON) |
| A9 docker build and run | **not done** | `evidence/docker-build.txt`, `evidence/docker-run.txt` (see section 5) |
| A10 UI build, `/v1` prefix | done | `evidence/ui-build.txt` |
| A11 no real network call in tests | done | guard tests `tests/e2e/test_network_guard_e2e.py::*`, `tests/integration/test_network_guard_integration.py::*` listed in `evidence/pytest-int-e2e.txt`; unit tests in `tests/unit/test_network_guard.py` |
| A12 CI jobs | done | `evidence/ci-yaml.txt`, `evidence/ddl-check.txt`, `evidence/compose-prod-check.txt` (lint plus DDL check, secret-scan with gitleaks, typecheck, unit plus OpenAPI snapshot, integration-e2e with service containers, migration-check) |
| A13 no secrets in diff | done | `evidence/secrets-grep.txt` (no match, tracked and untracked files) |
| A14 docs | done | `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md` (Decision 24), `CHANGELOG.md`, `planning/STATE.md` |

## 2. Files changed
Legend: **S000** = change already in the working tree from Sprint 000 or the UI rebrand (not this sprint). **S002** = this sprint. **S000+S002** = both touched it.

**Deps and settings**
- S002: `pyproject.toml` (S000 also edited the demo comment), `poetry.lock`, `core/settings.py` (new), `config.py` (S000+S002: S000 added the MODE check and renamed demo), `core/database/pool.py` (S000+S002), `.env.example` (S000+S002).
- S002 typing fixes, no behaviour change: `core/clients/async_http_client.py`, `core/clients/embeddings.py` (comment), `core/ingestion/chunkers.py`, `core/ingestion/readers.py`, `core/pipeline/db_ingest.py` (also B3 `source_filename`).

**Migrations and deploy**
- S002 (new): `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_baseline.py`. Deleted `core/database/schema.sql`.
- S002: `Dockerfile` (S000 also edited it), `docker-compose.prod.yml` (S000+S002; now no hardcoded credentials, `POSTGRES_PASSWORD` required), `scripts/setup_db.sh` (now creates the DB if missing and runs `alembic upgrade head`).

**API**
- S002: `api/main.py`, `api/errors.py` (new), `api/versioning.py` (new), `api/openapi.py` (new), `api/middleware/{logging,rate_limit,token_budget,finops}.py`, `api/mcp/{server,transport}.py`, `api/routers/{ingest,health,docs}.py`, `api/agent/graph.py`, `api/services/llm.py`, `claude_desktop_config.json`.
- S000 with S002 ruff whitespace fixes only: `api/agent/router.py` (S000: Koyeb/demo comment text; no S002 logic change), `api/models/schemas.py` (S000: `demo` to `public-preview` comments; S002: whitespace), `api/routers/search.py` (S000: comment text), `api/services/retriever.py` (S000 comment text; S002 whitespace in docstring).
- `api/observability.py` (new, S002).

**Tests (S002)**
- New: `tests/fakes.py`, `tests/harness.py`, `tests/db_fixtures.py`, `tests/integration/{test_migrations,test_ingestion_lifecycle,test_retrieval,test_usage_feedback,test_network_guard_integration}.py`, `tests/integration/fixtures/legacy_schema.sql`, `tests/e2e/{test_search_flow,test_errors_and_headers,test_mcp,test_network_guard_e2e}.py`, `tests/unit/{test_settings,test_errors,test_observability,test_middleware_paths,test_network_guard,test_typing_fixes,test_openapi_snapshot}.py`.
- Changed: `tests/conftest.py`, `tests/integration/conftest.py`, `tests/e2e/conftest.py`, `tests/unit/{test_llm,test_finops,test_agent_tools,test_config_mode}.py`. `test_config_mode.py` is S000 (untracked) and S002 added the DSN env lines. Ruff whitespace and import fixes only: `tests/unit/test_mcp_tools.py`, `tests/unit/test_usage.py`.
- Deleted: the two placeholder files.

**CI and scripts (S002)**
- `.github/workflows/tests.yml` (jobs: lint with a DDL check, secret-scan with gitleaks, typecheck, unit with the OpenAPI snapshot test, integration-e2e, migration-check).
- New: `scripts/check_no_ddl.sh`, `scripts/update_openapi.py`, `docs/openapi.json`.

**UI (S002)**: `ui/src/api/client.js`, `ui/src/api/ingest.js`, `ui/src/pages/Ask.jsx` (the rest of `ui/` is the S000 rebrand).

**Docs and planning**
- S002: `README.md` (S000 also edited it), `AGENTS.md` (S000 file, commands section edited), `docs/ARCHITECTURE.md` (moved in S000; S002 added Decision 24, `/v1` paths, replaced stale "demo" wording), `docs/architecture/FOUNDATION.md` (§4 row 7: schema diff deferred to when models exist), `docs/render-deployment.md` (S000+S002), `CHANGELOG.md`, `planning/STATE.md`, `planning/QUESTIONS.md`, this sprint folder.

## 3. Test numbers
- **Baseline:** unit collection failed (B1). Ruff: 33 errors.
- **Unit:** 149 passed, 0 failed, 0 errors.
- **Integration and e2e:** 66 passed, 0 failed, 0 skipped (22 integration, 44 e2e).
- **Whole suite in one run:** 215 passed.
- **A5 (Postgres stopped):** 66 skipped, 0 passed, 0 errors, a reason on every skip.
- **Ruff:** 0 errors. **mypy:** success, 58 files. **UI build:** success.

## 4. Problems and fixes
- **B1 (which side was wrong):** the test was wrong. Commit efde99f removed `classify_query_complexity` on purpose (routing now uses one configured model). `tests/unit/test_llm.py` is rewritten against `generate_with_citations` and `generate_with_routing`: 13 cases, up from 9 (citation hydration, hallucinated index, prompt content, model override, cost, unknown model, missing usage, truncation, rate-limit retry and give-up, non-retried errors, empty chunks, delegation).
- **B2 (which side was wrong):** the tests were wrong on the model, the config was incomplete on pricing. Config uses `gemini/gemini-3.5-flash-lite` (and `azure/gpt-4o` in prod). Groq was dropped on purpose. Tests now check the configured models and use `openai/gpt-oss-120b` (same rates) for the cost formula. The configured Gemini model had no pricing entry, so I added it at `$0 / $0` (free tier). No paid rate is invented (QUESTIONS B5).
- **`test_config_mode.py::test_public_preview_disables_reranker`:** now sets `DATABASE_URL` and `REDIS_URL`, because hosted modes require them by design. The assertions are unchanged.
- **Real bug found by mypy:** the MCP SSE route called `mcp._mcp_server`, which does not exist in MCP SDK 2.x, so no client could connect. Fixed with `_lowlevel_server`. A FastAPI endpoint function also sends a second response when the session ends and breaks under the middleware stack, so SSE is now a raw ASGI route at `/v1/mcp/sse`. A full MCP `initialize` round trip is tested.
- **SQLAlchemy 2.1** maps `postgresql://` to psycopg 3. `migrations/env.py` rewrites it to `postgresql+psycopg2://` (psycopg2 is already a dependency).
- **mypy 2.x** turns strict-ish flags on by default. The non-strict baseline is explicit in `pyproject.toml`. Strict is set per module for the three new modules.
- **RediSearch** cannot create indexes outside database 0, so the blueprint's "Redis DB 15 and FLUSHDB" is not possible with the real lifespan. Tests use db 0, delete only platform-owned key prefixes, and skip rather than touch a Redis holding other keys (QUESTIONS B7).
- **Middleware order changed** (needed so 429 bodies and headers carry `request_id` and `trace_id`): CORS, RequestID, Logging, Latency, RateLimit, TokenBudget, FinOps. Rate limit still runs before FinOps.
- **Logging:** the MCP SDK installs a Rich handler on import and litellm prints a banner on errors, so `setup_logging()` replaces all root handlers and silences the banner. A uvicorn run is now 100% JSON lines.
- **deepeval pytest plugin** crashed pytest's skip summary. Disabled with `-p no:deepeval` (it is only installed in the `labs` group).
- **Follow-up fixes after Architect review (B3, B4), both done:**
  - B3: `ingestion_pipeline` now takes `source_filename` and stores it in every chunk's metadata (the route passes the real upload name; default is the file's own name). Chunks ingested earlier still cite `unknown` until re-ingested. Regression tests: two integration tests in `test_ingestion_lifecycle.py`, plus e2e asserts the real filename in the LLM prompt and in agent citations.
  - B4: the usage dict in `api/services/llm.py` now also carries `model`, which FinOps reads. `usage_log.model` is the routed model and `X-Cost-USD` equals the logged cost. Regression tests: a unit test on the usage dict, the e2e flow asserting `row["model"]` and the header, and an e2e test with a priced model (non-zero cost, header equals logged cost).

## 5. Skipped items
- **A9 docker build and run: not done.** `docker build -t gap-api .` failed in two ways. First Docker Hub returned `429` for the base image (later it pulled). Then `pip install` inside the build container failed TLS verification (`CERTIFICATE_VERIFY_FAILED`) because this sandbox's egress proxy re-signs HTTPS and the build container does not trust it. Putting the proxy CA into a local base image, and a lint-only `docker build --check`, were both denied by the sandbox policy. I stopped there and did not work around it. Open decision for a human: run `docker build -t gap-api .` and `docker run` on a normal machine. What I did instead (`evidence/docker-run.txt`): ran the exact Dockerfile CMD (`alembic upgrade head && exec uvicorn ...`) against a fresh database. It migrated to `0001` and `/health` returned 200 with `db: ok`, `redis: ok`. The Dockerfile changes (copy `alembic.ini` and `migrations/`, new CMD) are therefore untested inside an image.
- `/health` shows `embedding: error` and `status: degraded` in the live run because no Ollama runs locally. This is expected.

## 6. Decisions and deferred costs
- `core/settings.py` raises `SettingsError` (a `ValueError`) with a short message that never contains values. `config.py` clears the settings cache on each import so `importlib.reload(config)` still works.
- `api/main.py` has a `create_app()` factory plus a module-level `app`, so each e2e test gets a fresh app and lifespan.
- Kept `/health` unversioned and also `/v1/health`. The unversioned one is hidden from OpenAPI.
- Rate limit and budget tests monkeypatch `config.RATE_LIMIT_REQUESTS` (the middleware now reads `config.X` at call time).
- **Deferred:** OpenTelemetry DB, Redis and LLM spans (Sprint 005); Alembic autogenerate and drift check (seam: `migrations/env.py` `target_metadata`); mypy strict outside the three new modules; `ignore_missing_imports = true` is global (third-party stubs); old `usage_log` rows keep their `/search` endpoint names next to new `/v1/search` rows; the raw `RateLimitMiddleware` still reads the request body for the SSE GET (existing behaviour).
- No per-module `ignore_errors` were needed, so there is nothing to list for step 7.
- Local dev DB `rag_platform` was created in the local Postgres container for the live runs.

## 7. STATE and CHANGELOG
Applied. `planning/STATE.md` (Now, Next, Platform today, Known gaps, Blockers) and `CHANGELOG.md` (Sprint 002 entry). `planning/QUESTIONS.md` has B5 to B7 (B3 and B4 were fixed and removed) and notes that Q3, B1 and B2 are resolved (a human should move them to `DECISIONS.md`). I did not edit `DECISIONS.md`.

## 8. Proposed commits (run by a human, branch `sprint/002-platform-base`)
The working tree also holds Sprint 000 and the UI rebrand, so add by path.
```bash
git checkout -b sprint/002-platform-base

# deps + settings
git add pyproject.toml poetry.lock core/settings.py config.py core/database/pool.py .env.example \
        core/clients/async_http_client.py core/clients/embeddings.py core/ingestion/chunkers.py core/ingestion/readers.py core/pipeline/db_ingest.py
git commit -m "feat(config): validated settings, mypy config and typing fixes"

# migrations
git add alembic.ini migrations/ Dockerfile docker-compose.prod.yml scripts/setup_db.sh
git rm core/database/schema.sql
git commit -m "feat(db): alembic migrations with idempotent baseline, drop schema.sql"

# api
git add api/main.py api/errors.py api/versioning.py api/mcp/ api/middleware/rate_limit.py api/middleware/token_budget.py \
        api/openapi.py api/middleware/finops.py docs/openapi.json scripts/update_openapi.py api/routers/ingest.py api/routers/health.py api/routers/docs.py api/agent/graph.py api/services/llm.py claude_desktop_config.json
git commit -m "feat(api): /v1 versioning, one error format, fix MCP SSE route"

# observability
git add api/observability.py api/middleware/logging.py
git commit -m "feat(observability): JSON logs, OpenTelemetry spans, X-Request-ID and X-Trace-ID"

# tests
git add tests/ 
git rm tests/e2e/test_e2e_placeholder.py tests/integration/test_integration_placeholder.py
git commit -m "test: real integration and e2e tiers, fakes, network guard; fix B1, B2"

# ci
git add .github/workflows/tests.yml scripts/check_no_ddl.sh
git commit -m "ci: lint, mypy, unit, integration+e2e with service containers, migration check"

# ui
git add ui/src/api/client.js ui/src/api/ingest.js ui/src/pages/Ask.jsx
git commit -m "feat(ui): call /v1 and read the standard error format"

# docs
git add README.md AGENTS.md docs/ARCHITECTURE.md docs/architecture/FOUNDATION.md docs/render-deployment.md CHANGELOG.md planning/STATE.md planning/QUESTIONS.md planning/sprints/002-platform-base/
git commit -m "docs: platform base sprint report, architecture decision 24, commands"
```
Note: `tests/` also contains `tests/unit/test_config_mode.py` (Sprint 000, untracked). Commit it with Sprint 000 or here. `ui/src/pages/Ask.jsx` also carries Sprint rebrand changes that were already uncommitted, so review `git add -p` for that file.

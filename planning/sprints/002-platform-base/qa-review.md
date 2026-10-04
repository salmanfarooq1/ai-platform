# Sprint 002: QA and code review

Reviewer re-ran every acceptance command. Product code and tests were not edited, nothing was committed.
Evidence is in `evidence/qa-*.txt` (A10 and A12 are re-run output and a copy of the file).

## Acceptance

| # | Check | Result | Evidence / note |
|---|---|---|---|
| A1 | ruff 0 errors | pass | `qa-A1-ruff.txt` |
| A2 | mypy success | pass | `qa-A2-mypy.txt` (57 files) |
| A3 | unit tests | pass | `qa-A3-unit.txt` (139 passed) |
| A4 | int+e2e, 0 failed, 0 skipped | pass | `qa-A4-int-e2e.txt` (66 passed, no skips) |
| A5 | Postgres stopped gives skips with reason | pass | `qa-A5-skip.txt` (66 skipped, reason on each; report said 63). Postgres restarted afterwards |
| A6 | migrate fresh and existing DB | pass | `qa-A6-migrate.txt`: `\d+` before/after identical except the new `alembic_version` table; fresh DB tables identical to old schema.sql |
| A7 | fail-fast settings | pass | `qa-A7-failfast.txt`: public-preview, prod and `MODE=bogus` all exit 1 with a clear message |
| A8 | live run | pass | `qa-A8-live-curl.txt`, `qa-A8-live-log.txt`: /health 200, /v1/health 200, /search 404 and /v1/search 422 in the error format, `X-Request-ID` and `X-Trace-ID` present, 20 of 20 log lines valid JSON |
| A9 | docker build and run | not verified | The egress proxy breaks TLS inside docker builds in this sandbox, so `docker build` was not run. The Dockerfile changes (COPY alembic.ini and migrations, new CMD) are untested inside an image |
| A10 | UI build, `/v1` prefix | pass | `qa-A10-ui.txt`: build succeeds; prefix is applied once in `apiFetch` (`ui/src/api/client.js:4,12`) |
| A11 | no real network in tests | pass | `qa-A11-guard.txt`: 3 guard tests (e2e x2, integration x1) run and pass in A4. Autouse guard in `tests/conftest.py` |
| A12 | CI jobs | pass | `qa-A12-ci.yml`: lint, typecheck, unit, integration-e2e (pgvector and redis-stack services, fails on any skip), migration-check. Not run on a real runner |
| A13 | no secrets in diff | pass | `qa-A13-secrets.txt` empty for the diff and for untracked files |
| A14 | docs updated | pass | AGENTS.md (migrate, mypy), README.md, docs/ARCHITECTURE.md (Decision 24), CHANGELOG.md, planning/STATE.md all contain Sprint 002 content |

## Findings

### High
None.

### Medium
1. **A9 is open.** The image, its migrate-then-serve CMD and the idempotent baseline on the hosted DB are untested inside a container. Fix: a human runs `docker build -t gap-api .` and `docker run` on a normal machine before deploy.
2. **FOUNDATION section 4 checks for rules 7, 8 and 14 are only partly in CI** (`.github/workflows/tests.yml`). Missing: a "no `CREATE TABLE` outside `migrations/`" check, a schema drift diff, an OpenAPI snapshot diff, and secret scanning. Rule 8 has only a local test (`tests/e2e/test_errors_and_headers.py:214`). Fix: add those steps, or write the deferral in `planning/QUESTIONS.md` (the report lists drift as deferred, not the others).
3. **Hardcoded DSN with a password in `docker-compose.prod.yml:~24`** (`postgres:postgres@postgres`). It is the pre-existing local compose DB, not a placeholder in app code, but it ships in the prod compose file. Fix: take it from `${DATABASE_URL}` or `${POSTGRES_PASSWORD}`.
4. **The working tree mixes Sprint 000 and the UI rebrand with this sprint** (about 50 UI files, `render.yaml`, `.gitignore`, `.dockerignore`, `api/routers/search.py`, `api/models/schemas.py`, `api/agent/router.py`, `api/services/retriever.py`, renames of ARCHITECTURE.md and BRANDING.md). The report discloses this, but `api/agent/router.py`, `api/models/schemas.py` and `api/routers/search.py` are not in its file list. Fix: stage by path as the report says, and add those three files to the list or commit them with Sprint 000.

### Low
1. `pyproject.toml:73` `addopts = "-p no:deepeval"` disables a plugin globally. It is explained in a comment and the tests do not use deepeval, but it hides the plugin for everyone. Fix: keep it, and note it in CONTRIBUTING.md.
2. `config.py:123` prices `gemini/gemini-3.5-flash-lite` at 0/0. This is the free tier and recorded as QUESTIONS B5, but every cost metric and the budget middleware read zero for the default model. Fix: confirm the rate and replace it.
3. `scripts/setup_db.sh` now creates the database but loads no schema, and hardcodes a container name. Fix: add `poetry run alembic upgrade head` as the last step.
4. `tests/unit/test_finops.py:26` computes the cost formula inside the test, so it checks arithmetic, not `finops.py`. This is pre-existing and was only repointed to another model. Fix: call the real cost function.
5. Counts in `report.md` section 3 differ from the re-run: A5 shows 66 skipped, not 63. Fix: correct the number.
6. `api/mcp/transport.py:22-26` has `noqa: F401` with no reason (the imports register MCP tools by side effect). Fix: add "registers tools on import". The `noqa` in `tests/e2e/conftest.py:71` has a reason.
7. `docs/ARCHITECTURE.md` (moved file) still uses "demo deployment" in an old decision. This is pre-existing text, and the "No demo wording" rule applies. Fix: reword to public-preview.
8. `tests/unit/test_config_mode.py:37` uses `MODE=demo` on purpose, to test rejection. No change needed.

## Rules and test review
- No test was skipped, deleted or weakened to get green. The two placeholder tests were replaced by real tiers. `test_llm.py` grew from 9 to 13 cases. The `test_config_mode.py` change only adds env setup, with the assertions unchanged.
- Test quality is good: the e2e and integration files assert bodies, DB rows, headers and logs, not only status codes (roughly 230 asserts against 17 status-code checks).
- The network guard blocks litellm entry points and every non-loopback socket and DNS lookup. No fake can reach the network.
- No secrets were found in the diff or the new files. `.gitignore` and `.dockerignore` now exclude `.env.*` except `.env.example`.
- No `type: ignore` was added. `noqa` is limited to the three F401 lines above.
- Docs are updated with the code, and `DECISIONS.md` was not edited, as the report says.

## Environment state
Postgres and Redis containers are running. The throwaway databases `qa_fresh`, `qa_exist` and `qa_live` were dropped. The uvicorn process was stopped.

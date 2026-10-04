# Sprint 002: Acceptance

Evidence goes in `evidence/`. Every file is captured command output.

- [x] **A1.** `poetry run ruff check api/ core/ tests/` → 0 errors. Evidence: `ruff.txt`
- [x] **A2.** `poetry run mypy` → "Success". Evidence: `mypy.txt`
- [x] **A3.** `poetry run pytest -m unit -q` → 0 failed, 0 errors (B1, B2 fixed). Evidence: `pytest-unit.txt`
- [x] **A4.** With `docker compose up -d postgres redis`: `poetry run pytest -m "integration or e2e" -q -rs` → 0 failed, 0 skipped. Evidence: `pytest-int-e2e.txt`
- [x] **A5.** Same command with Postgres stopped → tier is skipped with a reason, not passed or errored. Evidence: `pytest-skip.txt`
- [x] **A6.** Fresh DB: `alembic upgrade head` succeeds; DB built from the old `schema.sql` (from git: `git show HEAD:core/database/schema.sql`) then `alembic upgrade head` succeeds and `\d` output is identical before/after. Evidence: `migrate-fresh.txt`, `migrate-existing.txt`
- [x] **A7.** `MODE=public-preview` with no `DATABASE_URL` → app import/startup fails with a clear message. `MODE=bogus` fails. Evidence: `settings-failfast.txt`
- [x] **A8.** Live run: `uvicorn api.main:app` against local stack; `curl` `/health`, `/v1/health`, `/search` (404, error format), `/v1/search` with a bad body (422, error format). Headers include `X-Request-ID` and `X-Trace-ID`; server log lines are JSON. Evidence: `live-curl.txt`, `live-log.txt`
- [~] **A9 (not done: Docker build blocked in this sandbox, see report.md).** `docker build -t gap-api .` succeeds and the container runs migrations then serves `/health`. Evidence: `docker-build.txt`, `docker-run.txt`
- [x] **A10.** `cd ui && npm run build` succeeds; `grep -rn "'/v1" ui/src/api` shows the prefix. Evidence: `ui-build.txt`
- [x] **A11.** No real network LLM/embedding call during tests (guard fixture present and tested). Evidence: test name in `pytest-int-e2e.txt`
- [x] **A12.** CI workflow has lint, mypy, unit, integration+e2e jobs with service containers. Evidence: `ci-yaml.txt` (the file) 
- [x] **A13.** No secrets in diff: `git diff | grep -iE "api[_-]?key\s*=\s*['\"][A-Za-z0-9]"` empty. Evidence: `secrets-grep.txt`
- [x] **A14.** Docs updated: `AGENTS.md` commands (migrate, typecheck), `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, `planning/STATE.md`.

## Architect sign-off
Re-ran: ruff 0, mypy success (58 files), DDL guard OK, full suite 215 passed, workflow YAML parses. QA: 13/14 pass, findings closed.
Open: A9 (`docker build` + run) is not verified in the sandbox. Run it on a normal machine before the next deploy.

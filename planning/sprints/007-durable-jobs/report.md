# Sprint 007: Report

Built and tested in this container, except what is marked "not verified here". Nothing was committed or pushed. Evidence is in `evidence/` and is captured command output.

## 1. Acceptance

| Check | Status | Evidence |
|---|---|---|
| **A1** lint, mypy, DDL guard, full suite; frontend checks | **Done, with the standing MinIO skips.** ruff clean (`api core gateway ports adapters workers tests scripts/e2e`), mypy clean (126 files, `workers` added to its scope), DDL guard OK. Full suite 1181 passed, 0 failed, 10 skipped: the same 10 live-MinIO runs as the 006 baseline (`check_skips.py --expect 10` passes). "0 skipped" is not reachable without a MinIO image. Frontend: tokens check, lint, tsc, 182 Vitest, build, chunk report, copy check pass | `backend-ruff.txt`, `backend-mypy.txt`, `backend-ddl.txt`, `backend-pytest.txt`, `backend-skips.txt`, `frontend-checks.txt`, `frontend-vitest.txt`, `frontend-build.txt` |
| **A2** job tests | **Done.** Claim race (8 concurrent claims, one wins; two workers run 20 jobs, each exactly once and both take part); retry then success; backoff respected; max attempts gives `dead`; a permanent error fails at once; idempotency key (also 6 callers racing, per tenant); RLS as `gap_app` (no tenant sees nothing, cross-tenant insert refused, no DELETE); a real worker process killed with SIGKILL mid-job is re-claimed after its 2 s lease (attempt 2); a crash on the last attempt is `dead`; lost lease writes nothing; shutdown releases a long job without counting the attempt; stop of a queued and a running job; progress; migration 0008 incl. a non-superuser owner; `python -m workers` starts, reports health, runs a job and exits 0 on SIGTERM | `jobs.txt` (20 tests) |
| **A3** outbox tests | **Done.** The Postgres outbox bus passes the EventBus contract suite (3 adapters now, 22 tests). A rolled-back transaction publishes nothing (no row, relay sends nothing). A commit makes the row visible only after the commit. The relay is at least once (failed send retried and counted; a crash between send and mark sends twice) and two relays at once never send an event twice. Consumers dedupe by event id: LRU, `processed_events` across restarts, per consumer, a failing handler records nothing. RLS and no DELETE. Poison events stop after max attempts | `outbox.txt` (34 tests) |
| **A4** ingest 202, raw bytes once by sha256 | **Done.** 202 `{job_id, status: queued}`; the job is queued with no worker and runs to `succeeded` with progress done equal to total; the object is `<root>/<sha[:2]>/<sha>`, bytes equal; re-ingesting the same file, or under another name, adds no object and does not touch the old one; bytes are stored before parsing (kept when parsing fails); unchanged, updated and failed jobs; `Idempotency-Key` gives 200 and the same job and stores nothing twice; job routes are typed, gated (`kb:read`), tenant-scoped (foreign and missing give the same 404), paged, and hide KBs the policy hides; the ingest event is in the outbox in the job's transaction and a failed outbox write rolls the success back and retries | `ingest-jobs.txt` (15 tests) |
| **A5** agent run in the worker | **Done.** The graph runs in a worker slot (checked from inside the graph call); every decision of the run carries the job's `execution_id` and none of the request lacks it; usage booked once; a slow run answers 202 and `/v1/agent/runs/{id}` follows it queued to succeeded (also for an audit reader) and the 202 path books usage too; status survives a new runtime; a run keeps the boundary of the request that started it (a policy published while it waits does not apply); a crash is `failed` once, not retried, and its text is not in the run API; the AgentRuntime contract passes for the in-process and the queued runtime (26 tests), including stop during a tool call | `agent-worker.txt` (50 tests) |
| **A6** Playwright | **Done.** Upload in the Library returns "Queued", the row reaches "Ready", then Ask cites the new file. Whole suite 72 passed (71 before) | `playwright.txt` |
| **A7** docs | **Done.** ADR-0008 outbox section, new ADR-0011 (jobs, with Postgres `SKIP LOCKED` versus a broker), ADR-0009 note, ADR index, `ARCHITECTURE.md` (Decision 28, current state, gaps), README, `AGENTS.md`, `.env.example`, CHANGELOG, STATE, `docs/openapi.json` (snapshot test passes), `ui/src/api/schema.d.ts` regenerated. Q19 closed, Q21 to Q25 added | this report, `git diff` |

Also run: the live stale-vector script against a real API process with an embedded worker (`live-stale.txt`, all checks pass).

Not verified here: the live MinIO run (B12), the hosted (Neon) migration (0008 was tested with a non-superuser owner locally), CI on GitHub, a Docker image build, running the compose `worker` service, a human visual review of the Library and Agent runs pages, any real provider.

## 2. Test numbers
- Backend: **1181 passed, 0 failed, 10 skipped** (baseline 1097; the skips are the live MinIO runs). New or extended: `test_jobs.py` 16, `test_outbox.py` 12, `test_migration_0008.py` 3, `test_worker_process.py` 1, `test_ingest_jobs.py` 15, `test_agent_worker.py` 9, `test_jobs_units.py` 15, contracts (event bus +5, agent runtime +13), packaging +1.
- Frontend: **182 Vitest** (167 before), **72 Playwright** (71 before).

## 3. Existing tests that had to change (none weakened, skipped or deleted)
- **Ingest answers 202.** `tests/jobs_helpers.py` waits for the job and rebuilds the old answer, so the 30 call sites keep their assertions. `test_ingest_failures_do_not_leak_exception_text` now patches the worker's pipeline and asserts the job's error code and that no exception text reaches the job, its API or the answers (the log still has it): the 415 and 500 of the old route no longer exist. `test_logs_written_inside_the_request...` expects 202.
- **A worker runs the jobs.** The e2e `app` fixture starts one embedded worker and a temp object store; `second_app` stops the first app's worker (the "restart") so only the new adapters run the job. `test_a_client_that_disconnects_mid_run_stops_the_run` reads the run's status through the runtime instead of `runtime._runs`.
- **Defaults.** `test_registry` default bundle is now the outbox bus and the queued runtime; the override test passes in-process ones. `test_migrations` head is `0008` and the table list has the three new tables. `test_migration_0007` grants test migrates to `0007` (0008 adds grants). `test_gateway_packaging` includes `workers` in the image, lint and mypy scope and the compose worker. Contract fixture changes: runner outputs are JSON (`str(execution_id)`); the event bus suite uses a real tenant uuid.
- **UI.** Runs page tests: a Duration column, a mocked runs endpoint, `Queued`. `walkthrough.test` mock gets `status: 200` (new field of `ApiResult`).
- Harness: `truncate_tables` lists the new tables; `check_no_ddl.sh` and the import lint also scan `workers/`.

## 4. Deviations and decisions
- Extra `jobs` columns (`resource`, `result`, `error_detail`, `cancel_requested`, `started_at`, `finished_at`), `outbox.event_id`, `GET /v1/agent/runs` (list), an `execution_id` filter on `/v1/decisions`. `AgentQueryResponse` is an alias of `AgentResponse`. Q25.
- Outbox bus plus relay: subscribers on the bus run inline in the publisher's transaction (as before) and the relay feeds a separate target bus (Kafka in 010). That is how the unchanged contract suite passes.
- A failed ingest attempt is retried only for unexpected errors; a file nobody can read fails once (`unsupported_file`). Agent runs have 2 attempts: a failed run is not retried, only a run whose worker vanished.
- Booking of agent tokens and the `usage_log` row moved into the worker (once, where the run ends); FinOps skips them when `usage_booked`.
- A job's question is removed from the payload when the job ends; the answer stays in `jobs.result` (Q21).
- Reading a job writes a decision row (Q24).
- Embedded workers and relay (`EMBEDDED_WORKERS`, `EMBEDDED_RELAY`) added for one-process hosting and for tests; default off.

## 5. Problems and fixes
- `jobs.fail` sent a parameter the SQL did not use (asyncpg could not type it): fixed. The first full e2e run found it.
- Tests set the poll, beat and backoff intervals through `tests/conftest.py` before settings load.

## 6. Open questions
Q21 retention, Q22 stop route, Q23 hosting the worker, Q24 polling writes decisions, Q25 blueprint additions. Q19 closed.

## 7. Proposed commits (a human runs them; Sprint 005 to 006 are still uncommitted in this tree, see `COMMIT_PLAN.md`)
```bash
git add migrations/versions/0008_jobs_outbox.py core ports adapters workers api gateway config.py Dockerfile docker-compose.yml pyproject.toml .env.example .gitignore
git commit -m "feat: durable jobs, outbox and workers; ingest and agent runs as jobs"
git add tests scripts .github
git commit -m "test: jobs, outbox, worker process, ingest and agent-run end to end, runtime contract on two runtimes"
git add ui
git commit -m "feat(ui): Library shows ingest progress; agent runs from the runs endpoint; still-working state"
git add docs README.md AGENTS.md CHANGELOG.md planning
git commit -m "docs: ADR-0011, ADR-0008 outbox, ARCHITECTURE, Sprint 007 report"
```

## 8. QA fixes
Findings from `qa-review.md`. Each has a test that fails without the fix (L5 was checked by reverting the fix).

| Finding | Fix | Test |
|---|---|---|
| M1 runs API exposure | `jobs.namespace` and `jobs.principal_id` columns (in 0008, edited in place). Run routes show only allowed knowledge bases; without `audit:read` only the caller's own runs. ADR-0011 and ARCHITECTURE updated | `tests/e2e/test_agent_worker.py::test_m1_a_policy_that_hides_a_knowledge_base_hides_its_runs_and_answers`, `::test_m1_a_caller_without_audit_read_sees_only_its_own_runs` |
| M2 `/v1/jobs` misses agent runs | filters on the `namespace` column, not `payload` | `::test_m2_the_jobs_routes_hide_agent_runs_of_a_hidden_knowledge_base` |
| M3 double booking | `book_agent_usage` takes the `execution_id` and records it in `processed_events` first | `tests/integration/test_jobs.py::test_m3_usage_is_booked_at_most_once_per_execution_id` |
| L1 payload cap | cap is `max(4096, 4 * max_query_length)` for an agent run (`adapters/job_runtime.py`, `check_payload(limit)`) | `::test_l1_the_payload_cap_follows_the_questions_own_limit` |
| L2 exception text | not stored, not returned: 500 says "Agent execution failed", `error_detail` is null, the run error is `agent_run_failed` | `tests/e2e/test_ports_e2e.py::test_a_run_that_crashes_is_a_500_with_the_standard_error_and_a_failed_status`, `tests/e2e/test_agent_worker.py::test_a_crashing_run_is_failed_once_with_the_error_not_retried`, contract `test_a_failing_run_is_a_failed_result_with_the_error_not_an_exception[job-queue]` |
| L3 question in the log | the warning logs the execution id only | `tests/unit/test_jobs_units.py::test_l3_the_recursion_limit_warning_never_logs_the_question` |
| L4 | accepted, one line in ADR-0011 | none |
| L5 unreadable claimed job | released at once, attempt not counted (`workers/loop.py`) | `tests/integration/test_jobs.py::test_l5_a_claimed_job_that_cannot_be_read_is_given_back_at_once` |
| L6 helper assertion | the test now asserts the route's 202 and maps the job API's own status to the expected code | `tests/e2e/test_tenancy.py::test_ingest_failures_do_not_leak_exception_text` |

Expectations that changed because behaviour changed on purpose (L2): the two crash tests expected `Agent execution failed: model exploded` and `status.error == "model exploded"`; the runtime contract expects the text from the in-process runtime and the code `agent_run_failed` from the queued one.


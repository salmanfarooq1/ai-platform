# Sprint 007: QA and code review

The QA agent returned this as text, and the Architect saved it. The QA agent ran 56 targeted tests, and all passed.

**Architect full run:**
- Backend: 1181 passed, 10 skipped (live MinIO).
- Vitest: 182 passed.
- Playwright: 72 passed.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass (Architect) | ruff, mypy and the DDL guard are clean. The only skips are live MinIO. |
| A2 | pass | Claim race, retry, `dead`, idempotency, RLS, re-claim after lease |
| A3 | pass | Rollback publishes nothing. The relay is at least once. Consumers dedupe. |
| A4 | pass | 202 with a job. Raw bytes are stored once by sha256. |
| A5 | pass | The graph runs in the worker, and each decision carries the job's `execution_id`. |
| A6 | pass (Architect) | Playwright 72 of 72 |
| A7 | partial | The runs API exposure in M1 is not documented. |

## Findings
**High:** none.

**Medium**
- **M1:** `/v1/agent/runs` and `/v1/agent/runs/{id}` return every run's answer to the whole tenant, whatever the caller's knowledge-base limits.
- **M2:** the knowledge-base hiding on `/v1/jobs` misses agent runs, because it reads the namespace from `payload`, not from `resource`. It also leaks the hidden knowledge base's name.
- **M3:** agent usage is booked outside the job transaction. A re-claimed run can book it twice.

**Low**
- **L1:** the 4096-byte payload cap rejects long agent questions with 413, after the allow decision is recorded.
- **L2:** exception text is stored in `jobs.error_detail` and returned in the 500 response.
- **L3:** the question text is logged when the recursion limit is hit.
- **L4:** `jobs_tenant_of_execution` can be called with no tenant set.
- **L5:** a claimed job that cannot be read is held until its lease ends.
- **L6:** a status assertion in `test_ingest_failures_do_not_leak_exception_text` checks the helper, not the route.

## Architect disposition
- **Builder fixes, each with a test:** M1, M2, M3, L1, L2, L3, L5 and L6.
- **Accepted:** L4. The execution ids are random UUIDs. Documented in ADR-0011.

**Rules for the fixes:**
- **M1:** a caller sees only runs whose knowledge base its boundary allows. A caller without `audit:read` also sees only its own runs.
- **M3:** usage is booked at most once per `execution_id`.
- **L1:** the cap follows the policy's `max_query_length`.
- **L6:** the assertion is kept and made real, not removed.

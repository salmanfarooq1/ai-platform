# ADR 0011: Durable jobs on Postgres

**Status:** Accepted

## Context
Ingestion ran inside the request and agent run status lived in memory (Q19). A slow file held a connection, a restart lost a run, and nothing could retry. Sprint 007 needs a queue.

## Decision
- **The queue is a table, `jobs`, in the Postgres we already run.** A worker claims a job with `SELECT ... FOR UPDATE SKIP LOCKED` (`jobs_claim`, migration 0008), so two workers never get the same job. A claim sets a lease; a running job renews it every beat. A job whose lease ran out is claimed again, unless it used its last attempt (then it is `dead`) or somebody asked to stop it (then it is `failed`, code `stopped`).
- **States.** `queued`, `running`, `succeeded`, `failed` (will not run again: a file nobody can read, a run that crashed) and `dead` (used all attempts). A transient error goes back to `queued` with `run_after = now + base * 2^attempts` and jitter. Agent runs get 2 attempts, because a failed run is never retried, only a run whose worker disappeared.
- **Idempotency.** A unique index on `(tenant_id, idempotency_key)`; `INSERT ... ON CONFLICT DO NOTHING` decides, so callers racing with one key get one job.
- **Row-level security, forced.** Workers claim across tenants through a SECURITY DEFINER function that returns only a job id and its tenant. The handler then runs inside `tenant_connection` as `gap_app`. The owner role gets one extra policy so the function works when the owner is not a superuser. `gap_app` has SELECT, INSERT and UPDATE only.
- **Payloads hold no raw text over 4 KB.** Raw files go to the object store under their SHA-256 (stored once). An agent run's question is in the payload while the job is live and is removed when it ends.
- **The request context travels.** An agent job carries the principal and the boundary fixed at request start (`context_to_payload`), so a policy published while the job waits does not change it (strict rule 3).
- **The agent runtime is a job.** `JobAgentRuntime` implements `AgentRuntime` (ADR-0009): `start` enqueues, `status`, `wait` and `stop` read and write the job row. A worker runs the agent on an in-process runtime and stores the answer in `jobs.result`. It passes the same contract suite as the in-process runtime.
- **Stop.** A queued job is stopped at once; a running one gets `cancel_requested` and its worker cancels the handler (and so the tool call) at its next beat. If the worker never answers, `stop` ends the job itself.
- **Shutdown.** SIGTERM stops claiming; jobs in flight get `WORKER_SHUTDOWN_GRACE_SECONDS`, then their lease is released without counting the attempt.

## Postgres SKIP LOCKED versus a broker
- **For Postgres:** no new service to run, pay for or secure (the hosting is a free tier). The job row commits in the same transaction as the state it belongs to (the outbox event, the document registry), which a broker cannot do. Row-level security and the audit story stay in one place. At our rate (documents and agent runs, not millions of messages) `SKIP LOCKED` is far from its limit.
- **Against:** polling costs a query per worker per interval; a broker pushes. Throughput tops out at what one Postgres can do, and long transactions or heavy churn on the table need vacuum care. There is no fan-out or replay.
- **When to move:** if the claim query shows up in the database load, or a use case needs fan-out, ordering across consumers or replay, put a broker behind the same worker loop. Events already go out through the outbox and the `EventBus` port, so Kafka (Sprint 010) is an adapter, not a rewrite of the queue.

## Who sees a job or a run (QA fixes)
- **Knowledge bases.** A job has `namespace` and `principal_id` columns (migration 0008). `GET /v1/jobs`, `GET /v1/jobs/{id}`, `GET /v1/agent/runs` and `GET /v1/agent/runs/{id}` show only jobs whose knowledge base the caller's boundary allows. Anything else is the same 404 as a missing job, and the hidden knowledge base's name is not served.
- **Runs and `audit:read`.** `/v1/agent/runs` returns the answer text, so a caller without `audit:read` sees only the runs it started. An audit reader sees the tenant's runs (inside its knowledge-base limits).
- **Usage** of a run is booked at most once per `execution_id` (a marker row in `processed_events`, consumer `agent-usage`), so a run that a second worker re-claims does not book twice.
- **No exception text** is stored in `jobs.error_detail` for an agent run or returned to the caller (the 500 says "Agent execution failed"; the run has the code `agent_run_failed`). The text is in the worker's log. Logs never hold the question.
- **Payload cap.** The 4096-byte cap on a payload string is raised for an agent question to `4 * max_query_length` bytes, the most the gateway lets through.
- **A claimed job that cannot be read** is released at once (attempt not counted), not held until its lease ends.
- **Accepted (L4):** `jobs_tenant_of_execution` can be called with no tenant set. It returns one tenant id for an execution id, and execution ids are random UUIDs, so it cannot be used to guess or list runs.

## Consequences
- A worker must run for ingestion and agent runs. `docker compose up -d worker`, `python -m workers`, or `EMBEDDED_WORKERS=1` for a one-process host. Without one, `/v1/agent/query` answers 202 after the sync wait and the job waits.
- `jobs` has no retention yet (Sprint 008), and its rows keep a result (the answer text) under row-level security.
- Reading a job writes a decision row (every route goes through `enforce()`), so UI polling adds `kb.read` rows.
- Workers import from `api/` (the agent graph). They are one codebase, not a separate service.

# Sprint 007: Blueprint (contract first)

## 1. API contract (typed, `/v1`, OpenAPI)
| Method | Path | Scope | Response |
|---|---|---|---|
| POST | `/v1/ingest` | `kb:write` | **202** `JobAccepted {job_id, status: "queued"}`. Header `Idempotency-Key` is optional: the same key and tenant returns the same job with 200 |
| GET | `/v1/jobs/{id}` | `kb:read` | `Job {id, kind: "ingest"\|"agent_run", status: queued\|running\|succeeded\|failed\|dead, attempts, max_attempts, progress: {done, total}, error_code: str\|null, resource: str\|null, execution_id: uuid\|null, created_at, updated_at}`. Foreign or missing gives an identical 404 |
| GET | `/v1/jobs` | `kb:read` | Query: `kind`, `status`, `cursor`, `limit`. Returns `JobPage {items, next_cursor}` |
| POST | `/v1/agent/query` | `agent` | The response is unchanged when the run finishes within `AGENT_SYNC_WAIT_SECONDS` (default 25). Otherwise it's **202** `{execution_id, job_id}` |
| GET | `/v1/agent/runs/{execution_id}` | `agent` or `audit:read` | `AgentRun {execution_id, status, started_at, finished_at, result: AgentQueryResponse\|null, decisions_url}` |

Every route goes through `enforce()`. New actions need entries in `gateway/reasons.py` if they add reasons.

## 2. Data (migration 0008)
- **`jobs`**: `id`, `tenant_id`, `kind`, `status`, `payload jsonb` (no secrets, no raw text over 4 KB; raw bytes go to the object store), `idempotency_key`, `attempts`, `max_attempts` (default 5), `run_after`, `lease_until`, `locked_by`, `progress_done`, `progress_total`, `error_code`, `execution_id`, `created_at`, `updated_at`.
  - UNIQUE (`tenant_id`, `idempotency_key`) where the key is not null.
  - FORCE RLS.
  - `gap_app` gets SELECT, INSERT and UPDATE.
- **`outbox`**: `id`, `tenant_id`, `event jsonb` (a CloudEvent), `created_at`, `published_at`, `attempts`.
  - FORCE RLS.
  - Written in the same transaction as the state change.
- **Claim:** `UPDATE jobs SET status='running', lease_until=now()+lease, locked_by=$w, attempts=attempts+1 WHERE id = (SELECT id FROM jobs WHERE status IN ('queued') AND run_after<=now() OR (status='running' AND lease_until<now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *`.
  - Workers are tenant-agnostic. They need a narrow SECURITY DEFINER claim function, in the existing pattern, that returns only the job's tenant and id.
  - The work itself then runs inside `tenant_connection` as `gap_app`.
- **Backoff:** `run_after = now() + base * 2^attempts` with jitter. A job that reaches `max_attempts` goes to `dead`.

## 3. Components
- **Worker loop:**
  - `workers/` with `python -m workers --concurrency N`.
  - Graceful shutdown on SIGTERM: it finishes the current job or releases the lease.
  - A health file or log line.
- **Ingest job:**
  1. Put the raw bytes in the ObjectStore (sha256 key; the same bytes are written once).
  2. Parse, chunk, embed and store.
  3. Update progress per batch.
  4. Write a `platform.ingest.completed.v1` event to the outbox.
- **Agent run job:** it runs through `AgentRuntime.start` (006) inside the worker. Every decision carries the `execution_id`.
- **Outbox relay:** it polls `outbox WHERE published_at IS NULL`, publishes through the EventBus port, and marks the rows sent. It's at least once. The in-process adapter dedupes by CloudEvent `id` (an LRU plus a `processed_events` table for durable consumers).
- **Postgres outbox EventBus adapter:** it must pass the 006 EventBus contract suite.

## 4. UI (follows `docs/design/`)
- **Library:** each document row shows its job status and progress. It polls `/v1/jobs?kind=ingest` with TanStack Query: every 2 s while any job is queued or running, then it stops. Failed and dead jobs show `error_code` with a plain sentence.
- **Upload:** it returns at once and shows "Queued".
- **Agent runs page:** it reads `/v1/agent/runs` (list by decisions plus runs) and shows status, `execution_id` and duration.
- **Ask in Agent mode:** if the run takes longer than the sync wait, it polls the run and shows a quiet "Still working" state. There are no spinners on console tables.

## 5. Compose
A `worker` service in `docker-compose.yml`, using the same image as the API with the command `python -m workers`. Local dev documents running a worker.

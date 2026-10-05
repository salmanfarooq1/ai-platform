# Sprint 007: Durable jobs and raw storage. Requirements

A vertical slice: backend jobs and outbox, plus the Library ingestion progress screen.

## Contract first
- `POST /v1/ingest` returns `202 {job_id}` instead of ingesting inside the request.
- `GET /v1/jobs/{id}` returns `{id, kind, status: queued|running|succeeded|failed|dead, attempts, progress: {done, total}, error_code, created_at, updated_at}`.
- `GET /v1/jobs?kind&status&cursor` lists jobs.
- All three are typed, under `/v1`, in the OpenAPI snapshot, under RLS, and gated by `enforce()`.

## Scope
1. **Queue (migration 0008):** a `jobs` table with FORCE RLS. Workers claim jobs with `SELECT … FOR UPDATE SKIP LOCKED`.
   - Retries with backoff and a max of attempts, after which the job goes to `dead`.
   - An idempotency key unique per tenant: the same key returns the same job.
   - Workers run as `gap_app` with `tenant_connection`.
2. **Transactional outbox behind the EventBus.** An `outbox` table is written in the same transaction as the state change. A relay publishes the rows and marks them sent, at least once.
   - The Postgres outbox adapter must pass the 006 EventBus contract suite.
   - Consumers dedupe by CloudEvent `id`.
3. **Ingestion moves to a worker.** Raw files are stored in the ObjectStore by sha256 before parsing, and the same bytes are stored once.
4. **Agent runs move to a worker through AgentRuntime.**
   - `/v1/agent/query` keeps its synchronous contract: it waits up to the request timeout and then returns `202 {execution_id}`.
   - A runs status endpoint backs the Agent runs page.
5. **Worker entry point:** `python -m workers`. Docker compose gets a `worker` service.
6. **UI:**
   - The Library shows each document's job status and progress, polling with TanStack Query and backing off when idle.
   - The Agent runs page uses the runs endpoint.

## Out of scope
Kafka (010). Retention (008).

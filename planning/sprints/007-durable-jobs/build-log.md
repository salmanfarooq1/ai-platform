# Sprint 007 build log

Plan: migration 0008 (jobs, outbox, processed_events, three SECURITY DEFINER functions); `core/database/jobs.py`;
outbox adapter and relay; queued AgentRuntime; `workers/` (loop, handlers, embedded); routes; tests; UI; docs.

- Built the backend, migration and workers. Existing tests moved to a `settle` helper that waits for the ingest job.
- Bug: `jobs.fail` sent an unused parameter (asyncpg could not type it). Fixed.
- Resumed after an API limit and a container restart: the working tree was intact. Fixed the migration head
  assertions, the registry defaults test, regenerated `docs/openapi.json`.

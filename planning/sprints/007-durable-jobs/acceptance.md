# Sprint 007: Acceptance
- [ ] **A1.** ruff, mypy, DDL guard and the full suite pass with 0 skipped. The frontend lint, tsc, vitest and build pass. Evidence: `backend-*.txt`, `frontend-*.txt`
- [ ] **A2.** Job tests cover:
  - a claim race with two workers (no double run)
  - retry then success
  - max attempts gives `dead`
  - an idempotency key returns the same job
  - RLS as `gap_app`
  - a worker crash mid-job is re-claimed after the lease expires

  Evidence: `jobs.txt`
- [ ] **A3.** Outbox tests: the Postgres outbox adapter passes the EventBus contract suite. A rolled-back transaction publishes nothing. The relay is at least once and consumers dedupe. Evidence: `outbox.txt`
- [ ] **A4.** Ingest returns 202. The raw bytes are stored once by sha256, and re-ingesting the same file creates no new object. Evidence: `ingest-jobs.txt`
- [ ] **A5.** An agent run executes in the worker through AgentRuntime, and its decisions carry the `execution_id`. Evidence: `agent-worker.txt`
- [ ] **A6.** Playwright: upload a document, watch its progress reach "Ready" in the Library, then ask a question that cites it. Evidence: `playwright.txt`
- [ ] **A7.** Docs are updated: ADR-0008 gets an outbox section, plus README, ARCHITECTURE and the OpenAPI snapshot.

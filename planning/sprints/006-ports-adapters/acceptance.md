# Sprint 006: Acceptance

- [ ] **A1.** ruff, mypy (strict on `ports/` and `adapters/`), DDL guard, unit tests: 0 failed. Evidence: `ruff.txt`, `mypy.txt`, `pytest-unit.txt`
- [ ] **A2.** int+e2e+contracts: 0 failed, 0 skipped (except a documented MinIO skip, if the image can't be pulled). Every earlier test still passes with unchanged assertions. Evidence: `pytest-int-e2e.txt`
- [ ] **A3.** `grep -rn "import litellm\|langchain_litellm\|import redis\|from redis" api core gateway` finds nothing. The import-lint test passes. Evidence: `grep-imports.txt`
- [ ] **A4.** Each port has a contract suite, run against ≥ 2 implementations. Evidence: test ids in `pytest-int-e2e.txt`
- [ ] **A5.** Migration 0007 on data: counts are kept, and every row has a model and dimension. Evidence: `migrate.txt`
- [ ] **A6.** Live run: ingest, then search, works. Change `EMBED_MODEL`, restart, and search finds none of the old chunks while `/v1/health` shows `stale_vectors > 0`. Evidence: `live-stale.txt`
- [ ] **A7.** ADR-0005 (updated), ADR-0008 and ADR-0009 and the docs are updated. OpenAPI snapshot refreshed (health field). No secrets.
- [ ] **A8.** `report.md` has a requirement → tests table, and lists every moved function (from → to).
- [ ] **A9.** EventBus contract suite passes on the in-process adapter. Every recorded decision publishes one `platform.gateway.decision.v1` CloudEvent with no input text. Evidence: `eventbus.txt`
- [ ] **A10.** AgentRuntime contract suite (start, status, stop, cleanup, stop during a tool call) passes on the in-process adapter. `/v1/agent/query` runs through it. Every decision a run causes carries its `execution_id`. Evidence: `agent-runtime.txt`
- [ ] **A11.** The Agent runs page shows `execution_id` and the status, with a Vitest test and the Playwright suite still green.

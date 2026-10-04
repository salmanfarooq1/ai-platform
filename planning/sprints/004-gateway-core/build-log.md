# Sprint 004: Build log

## Plan
1. Baseline: 492 tests pass at head 0004.
2. Migration 0005: `policies` (append-only, one active per tenant) and `gateway_decisions`, RLS forced, explicit grants to `gap_app` (policies SELECT; decisions SELECT, INSERT).
3. `gateway/` package: types, boundary, policy, stages, limits, record, enforce.
4. Wire routes (`gateway_context` dependency), agent (boundary through RunnableConfig), MCP, errors; move rate and budget out of middleware, fail closed on Redis errors (QA M2).
5. Admin CLI `set-policy` / `show-policy`; import-lint test; unit, integration, e2e tests.
6. Live run with two tenants, evidence, ADR-0006, docs, OpenAPI snapshot.

## Log
- Baseline 492 passed. Wrote migration 0005, gateway/ package, wiring (routes, agent, MCP, errors, FinOps), CLI. Existing tests needed fixture-only edits: policy/recorder stubs for unit tests, agent tool config now carries the gateway context, harness TRUNCATE lists the two new tables, migration head/table-set expectations.
- Tests: unit (stages, fail-closed over every stage, boundary property tests at 300 examples, policy validation, error mapping, import lint, packaging), integration (versioned policies, append-only triggers, RLS on both tables, one row per enforce, broken policy row, mid-request policy change, 0005 on a 0004 database with data, CLI), e2e scenarios 1-4, 6, 7, 9 plus extras. Scenario 5 is the unchanged Sprint 003 rate and budget tests; scenario 8 is the unit import-lint test.
- Found while writing the Dockerfile check: the runtime stage copies packages one by one, so `gateway/` was missing from the image. Added the COPY line and a test.
- Mutation check: turning the deny into an allow in `enforce()`, and removing the Redis fail-closed raise in `limits.py`, each made the new tests fail (restored afterwards).
- Live run on a throwaway database with two tenants and different policies (fake LLM through a scratch launcher outside the repo): 200, 403 by KB, 403 by model, 400 by guardrail; psql rows and a pg_dump grep with 0 hits for the query text; Redis container stopped and restarted to show 503 `dependency_unavailable`. Throwaway database dropped and key files removed afterwards.
- Mistake and fix: a `git rm --cached` on the two middleware files staged their deletion; undone with `git reset HEAD -- <the two files>` (the index is as before) and the files were removed from disk.
- Final: ruff, mypy, check_no_ddl clean; 667 passed, 0 failed, 0 skipped.

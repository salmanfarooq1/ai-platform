# Sprint 006: Build log

## Plan
1. Baseline: 875 tests pass (unit + integration + e2e), 0 skipped.
2. `ports/` Protocols and frozen dataclasses (LLM, chat model, embeddings, knowledge store, cache, object store, event bus, agent runtime). mypy strict on `ports/` and `adapters/`.
3. Move code into `adapters/` one port at a time, full suite after each: embeddings, LLM + chat, knowledge store, cache (and limits), object stores, event bus, agent runtime.
4. `adapters/registry.py` composition root, wired in `api/main.py`; call sites take ports.
5. Migration 0007 (embedding provenance, `execution_id`), retrieval filters on the active model, `stale_vectors` in health.
6. Fakes become adapters; test app built from the registry; `tests/contracts/`.
7. Import-lint extended; empty modules deleted.
8. UI touch on the Agent runs page; ADR-0005 update, ADR-0008, ADR-0009, docs, CHANGELOG, STATE.
9. Evidence in `evidence/`, `report.md` last.

## Log
- Baseline captured: 875 passed, 0 skipped (164 s).
- Wrote `ports/` and `adapters/` (litellm_llm, litellm_chat, litellm_embeddings, pg_knowledge, redis_cache, local and s3 object stores, in-process event bus and agent runtime, registry). Rewired routes, gateway limits and record, agent tools and graph, MCP, web edge, health and `api/main.py` lifespan to take ports. Migration `0007` written.
- Moved all tests' provider seams to the fakes (fixtures and call signatures only). `tests/unit`: 522 passed after the move (was 424 plus new import-lint tests).
- Adapters moved. I did not run the full suite after each single port: the fakes, fixtures and call sites of the ports depend on each other (a route takes several ports at once), so the tree was not runnable until the seams were all in. Instead I ran the unit tier after the move (522 passed) and the integration, e2e and contracts tiers after each batch of fixes. Logged here as a deviation.
- Broke and fixed:
  - Old tests patched `litellm` and `app.state.redis`. The fixtures now hand fakes to `create_app(adapter_overrides=...)`, and `redis_raw` is a plain client for looking at keys. Assertions kept; a few changed where the contract itself changed (see report).
  - `test_rls` seeds raw `documents` rows: added the new not null columns to the fixture inserts.
  - Redis semantic filter with an empty model tag was a RediSearch syntax error: the adapter uses a placeholder tag for "no model".
  - `test_route_tenant_inputs` (AST check) rejected a `tenant_id` parameter and `status.tenant_id` in a router: the run-status helper moved to `api/services/run_status.py`.
  - mypy strict on `ports/` and `adapters/`: typed the Redis client as Any (redis-py stubs are sync-and-async in one), added a not-None check before a row is built.
  - The hosted-owner test found that `SELECT id FROM tenants` needs the migration role to own `tenants`; the test now runs every migration as a non-superuser owner, as on Neon.
  - The Dockerfile runtime stage copied only api, core and gateway: added ports and adapters (the image would not have started).
  - CI failed on any skipped test: the one allowed skip is the live MinIO run.
- Found: `litellm.completion_cost` does not take token arguments, so the agent's best-effort cost always raised and was swallowed. Moved as it was (refactor), recorded as Q18.
- MinIO: `docker pull minio/minio` is denied here, quay.io is forbidden. The S3 adapter runs the contract suite against an in-memory client. `scripts/verify/minio.sh` written, live run not verified here.
- UI: Agent runs page shows the execution id and status (`run-status.ts`), 5 Vitest tests and 1 Playwright test added. Tokens check, lint, tsc, 167 Vitest, build, chunk-report, copy-check and 71 Playwright tests pass.
- Evidence captured in `evidence/`. Final numbers: unit 543 passed; integration, e2e and contracts 541 passed, 10 skipped (live MinIO); ruff, mypy and the DDL guard clean.

# Sprint 006: Ports and adapters: Blueprint

## Read first
`AGENTS.md`, ADR-0005, ADR-0006, `core/settings.py`, `config.py`, `api/services/{llm,retriever,cache,usage}.py`, `core/clients/embeddings.py`, `core/ingestion/lifecycle.py`, `core/pipeline/db_ingest.py`, `core/database/bulk_ops.py`, `api/routers/*.py`, `api/agent/graph.py`, `api/mcp/*.py`, `gateway/limits.py`, `gateway/record.py`, `tests/fakes.py`, `tests/db_fixtures.py`, `tests/import_lint.py`.

## Steps
1. Write `ports/` (Protocols + frozen dataclasses). These are the contracts, so mypy runs in strict mode on `ports/` and `adapters/`.
2. Move the code, without rewriting it, into adapters one port at a time. After each port, run the full suite. Keep SQL text identical unless the tenant or provenance changes require otherwise.
3. Add `adapters/registry.py`. Wire it in the `api/main.py` lifespan.
4. Rewrite the call sites to take ports, via `request.app.state.adapters` or the gateway context.
5. Migration `0007_embedding_provenance.py`: add the columns, backfill, set `not null`, add the index. Grants for `gap_app` don't change (same table).
6. Make retrieval filter on the active model and dimension. Add `stale_vectors` to health.
7. Turn the fakes into port adapters. Build the test app from the registry with fakes. Add `tests/contracts/` with parametrized suites.
8. Extend the import-lint. Delete the now-empty modules.
9. Docs: ADR-0005 update (registry and composition root), ADR-0008 (event bus), ADR-0009 (agent runtime), ARCHITECTURE, AGENTS (how to add a provider), CHANGELOG, STATE.

## Tests
- **Contract suites:** LLM (fake, and litellm with the network guard → must raise cleanly), embeddings (fake, plus dimension check), knowledge store (pg vs fake in-memory, run against real Postgres as `gap_app`), cache (redis vs fake dict), object store (local vs S3 on MinIO if available).
- **Integration:** migration 0007 on data from 0005 (counts and backfill). Stale vectors are excluded and counted.
- **E2E:** the full existing suite keeps passing. A test switches the embedding model setting and shows that search returns no stale matches and health reports the count. Embedding fallback succeeds on the same dimension and is refused on a different one.
- **Import-lint:** passes on the tree, and fails on an injected violation for each banned module.

## Walking skeleton
- **Deferred:** a re-embedding job for stale vectors (006 adds the queue; the seam is the `stale_vectors` count), and per-adapter OTel spans.
- **Bounded:** one registry and no plugin system.

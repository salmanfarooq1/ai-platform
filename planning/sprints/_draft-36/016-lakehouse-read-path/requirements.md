# Sprint 016: Lakehouse read path. Requirements

Vertical slice, M4 (Data Plane). Read tenant lakehouse tables through the gateway, on locked DuckDB connections.

## Scope
1. Query engine.
   - `QueryEngine` port (`ports/query_engine.py`) and a DuckDB adapter (`duckdb==1.5.5`, DuckLake 1.0 extension installed in the image).
   - New package `dataplane/`. `duckdb` joins the import-lint SDK list.
2. Per-tenant catalogs.
   - Database `lakehouse`, created by `scripts/setup_db.sh` and the test fixture.
   - One metadata schema, one data path prefix and one SeaweedFS identity (limited to its prefix) per tenant.
   - A catalog role separate from `gap_app`. Catalog and S3 secrets never reach agents.
3. Locked connections and process model.
   - Attach only the caller's tenant catalog (read only for reads).
   - Then `enable_external_access=false`, allowed paths, no extension autoinstall or autoload, unsigned refused, `memory_limit`, `threads`, a timeout, `lock_configuration=true`.
   - Reads on a thread pool with a bounded tenant-keyed connection cache. Heavy queries on a query worker.
4. Gateway.
   - New action kind `data.read`. Also update `KNOWN_TOOLS` and the reason codes.
   - Every read pins one catalog-wide snapshot id, and the decision record v2 carries it in the `data` extension.
   - The `DataAccess` port (013) gets its real adapter, with `read` and `current_snapshot`.
5. API, verify and ADR.
   - `GET /v1/data/datasets/{id}/preview` and `GET /v1/data/datasets/{id}/snapshots`, governed.
   - New credential scope `data:read` for these routes. `GET /v1/system/modules` keeps `kb:read`.
   - `scripts/verify/ducklake.sh`.
   - ADR-0015, with the written exception to strict rule 7.

## Out of scope
- Writes, uploads, dataset registry, maintenance (017). Free SQL, grants, masking (023, 024, 026).
- Agent access to data (027).

## Nav placement
Data > Datasets: a read-only list and a preview.

## Questions this sprint closes
- None from the open list.

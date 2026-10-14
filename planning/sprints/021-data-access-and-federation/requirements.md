# Sprint 021: Data access and federation. Requirements

Data pillar (M4), on the Gateway. Read client data where it lives, through the gateway, on locked connections. Copy nothing unless a later pipeline says why (rule 12).

Source: old 016, plus new scope (integration-data-connectors research note).

## Scope
1. **Connection registry.**
   - A `connections` table (RLS) holding the kind (`postgres`, `mysql`, `sqlite`, `files`, `excel`, `trino`, later `snowflake`, `bigquery` and `databricks`), the display name, owner and a secret reference. The secret itself is never stored.
   - Secrets come from mounted secret files now. OpenBao arrives in 031.
   - Each connection is read-only by contract. The docs give the client a "narrow read-only role" recipe for each kind.
   - A `connection.test` action checks reachability and privileges. It refuses a role that can write.
2. **`DataAccess` adapters**, all behind one port, all taking the same compiled grant and returning the same receipt fields.
   - **Direct:** DuckDB (`duckdb==1.5.5`) `ATTACH ... (READ_ONLY)` to the client Postgres, MySQL or SQLite, and reads of files and Excel from an allowed path. The attach happens first. Then `enable_external_access=false`, no extension autoinstall or autoload, unsigned extensions refused, `memory_limit`, `threads`, a timeout, and `lock_configuration=true`. The Builder checks that this order works with each scanner and records it.
   - **Lakehouse:** DuckLake 1.0 for data we hold. One catalog for a single-tenant deploy, and one per tenant in multi-tenant deploys (catalog role separate from `gap_app`, data prefix and SeaweedFS identity per tenant, cross-tenant negative tests).
   - **Federated (spike):** Trino with the OPA access-control plugin, in its own compose profile `federation`. The spike shows one join across two sources. Trino applies a row filter and a mask from our policy bundle. Results go in `evidence/spike-trino.md`. The full adapter lands in 024 if the spike passes.
   - `duckdb` and the Trino client join the import-lint SDK list. New package `dataplane/`.
3. **Process model.** Reads run on a thread pool with a bounded connection cache keyed by tenant and connection. Heavy queries run on a query worker. No writes in this sprint.
4. **Gateway.**
   - New action kind `data.read`, with `KNOWN_TOOLS` and reason codes updated.
   - Record v2 extension `data`: `connection_id`, `adapter`, `engine_version`, plus `snapshot_id` when the source has one (DuckLake) or `as_of` and `replayable: false` when it does not (a live client database).
   - The receipt states honestly whether the read can be replayed.
   - SQL parse base: `sqlglot` parses every query, and only one SELECT is allowed. The full rewrite and guard come in 024 and 025.
5. **API and UI.**
   - `/v1/data/connections` (create, test, list) under `admin`.
   - `GET /v1/data/datasets/{id}/preview` and `.../snapshots`, governed, with the new scope `data:read`.
   - `scripts/verify/ducklake.sh` and `scripts/verify/direct-postgres.sh` against the 014 source database.
6. **ADR-0015 (revised):** data access adapters, locked connections, gateway-only access, and the written exception to strict rule 7 for the DuckLake catalog.

## Out of scope
- Writes, uploads, pipelines, maintenance (022). Grants, masking and free SQL (024, 025).
- Native warehouse adapters (Snowflake, BigQuery, Databricks). The port allows them; they are built when a client needs one.
- Agent access to data (027).
- Changed from old 016: reading in place comes first. The per-tenant catalog applies only to multi-tenant deploys.

## Nav placement
- Data > Connections: list, add, test.
- Data > Datasets: a read-only list and preview, showing whether the data is "read in place" or "held".

## Questions this sprint closes
- Proposes a default for owner question Q-09 (who holds client credentials): secret files now, OpenBao in 031.

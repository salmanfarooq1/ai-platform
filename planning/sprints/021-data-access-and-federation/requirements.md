# Sprint 021: Data access and federation. Requirements

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Data pillar (M4), on the Gateway. Read client data where it lives, through the gateway, on locked connections. Copy nothing unless a later pipeline says why (rule 12).

Depends on: Sprint 018.

## Scope
1. **Reference data first.** `data/reference-company/generate.py --size small|medium --seed N --out DIR` writes CSVs for `fin_invoices`, `fin_invoice_lines`, `fin_ledger_entries`, `fin_budgets`, `crm_accounts`, `crm_contacts`, `crm_opportunities`, `hr_employees` and `hr_salaries`; deterministic invoice and contract PDFs; and a manifest. Small data has 50 accounts, 1,000 invoices and 40 employees. Medium data has 2,000 accounts, 100,000 invoices and 400 employees. A column-classified data dictionary and safe-value checks cover every generated table. `checksums.json` holds expected manifest hashes per size and seed.
   - Add the bounded client-schema variant. It generates files from a documented schema format with consistent keys. It does not load a client schema into a database.
   - Run `refco_source` in its own container in Compose profile `lake`, not in the platform Postgres service. `load_source.py` uses a separate forward-only migration tree and a read-only `refco_reader` role. This proves read-in-place access against a separate source.
   - Add `change_generator.py --seed S --steps N`. Each insert, update or delete step is replayable and records before/after hashes atomically.
   - Pin Faker and reportlab in the dev dependency group. A version bump requires a reviewed checksum update.
2. **Connection registry.**
   - A `connections` table (RLS) holding the kind (`postgres`, `mysql`, `sqlite`, `files`, `excel`, `trino`, later `snowflake`, `bigquery` and `databricks`), the display name, owner and a secret reference. The secret itself is never stored.
   - Secrets come from mounted secret files now. OpenBao arrives in 031.
   - Each connection is read-only by contract. The docs give the client a "narrow read-only role" recipe for each kind.
   - A `connection.test` action checks reachability and privileges. It refuses a role that can write.
3. **`DataAccess` adapters**, all behind one port, all taking the same compiled grant and returning the same receipt fields.
   - **Direct:** DuckDB (`duckdb==1.5.5`) `ATTACH ... (READ_ONLY)` to the client Postgres, MySQL or SQLite, and reads of files and Excel from an allowed path. The attach happens first. Then `enable_external_access=false`, no extension autoinstall or autoload, unsigned extensions refused, `memory_limit`, `threads`, a timeout, and `lock_configuration=true`. The Builder checks that this order works with each scanner and records it.
   - **Lakehouse:** DuckLake 1.0 for data we hold. One catalog for a single-tenant deploy, and one per tenant in multi-tenant deploys (catalog role separate from `gap_app`, data prefix and SeaweedFS identity per tenant, cross-tenant negative tests).
   - **Federated (default, `QUERY_ENGINE=duckdb`):** first, before any other adapter work, prove one real join across a client Postgres and a SQLite file in one DuckDB session under the locked settings above. Record the plan, timings on medium data and memory in `evidence/duckdb-join.md`. If it fails, stop and bring it to the Architect.
   - **Federated at scale (optional, `QUERY_ENGINE=trino`):** not built here. The `DataAccess` contract suite is written so a Trino adapter can be added later and must pass the same suite (ADR-0035).
   - `duckdb` joins the import-lint SDK list. New package `dataplane/`.
4. **Process model.** Reads run on a thread pool with a bounded connection cache keyed by tenant and connection. Heavy queries run on a query worker. No writes in this sprint.
5. **Gateway.**
   - New action kind `data.read`, with `KNOWN_TOOLS` and reason codes updated.
   - Record v2 extension `data`: `connection_id`, `adapter`, `engine_version`, plus `snapshot_id` when the source has one (DuckLake) or `as_of` and `replayable: false` when it does not (a live client database).
   - The receipt states honestly whether the read can be replayed.
   - SQL parse base: `sqlglot` parses every query, and only one SELECT is allowed. The full rewrite and guard come in 024 and 025.
6. **API and UI.**
   - `/v1/data/connections` (create, test, list) under `admin`.
   - `GET /v1/data/datasets/{id}/preview` and `.../snapshots`, governed, with the new scope `data:read`.
   - `scripts/verify/ducklake.sh` and `scripts/verify/direct-postgres.sh` against the 014 source database.
7. **ADR-0015 (revised):** data access adapters, locked connections, gateway-only access, and the written exception to strict rule 7 for the DuckLake catalog.

## Out of scope
- Writes, uploads, pipelines, maintenance (022). Grants, masking and free SQL (024, 025).
- Native warehouse adapters (Snowflake, BigQuery, Databricks). The port allows them; they are built when a client needs one.
- Agent access to data (027).
- Read-in-place access comes first. The per-tenant catalog applies only to multi-tenant deploys.
- Re-planned 2026-11-08: see "Re-plan 2026-11-08" in `planning/program/sprint-map.md` and ADR-0035. The Trino spike was replaced by the DuckDB join proof; Trino is optional.

## Nav placement
- Data > Connections: list, add, test.
- Data > Datasets: a read-only list and preview, showing whether the data is "read in place" or "held".

## Questions this sprint closes
- Proposes a default for owner question Q-09 (who holds client credentials): secret files now, OpenBao in 031.

# Sprint 017: Lakehouse write path. Requirements

Vertical slice, M4 (Data Plane). Datasets get a registry, data arrives through jobs, and snapshots are kept, expired and erased on purpose.

## Scope
1. Dataset registry.
   - Tables `datasets`, `dataset_tables`, `dataset_schema_versions`, each with `tenant_id`, RLS and a `GRANT` to `gap_app`.
   - Additive schema changes are automatic. Other changes are refused until contracts exist (021).
2. Upload to table.
   - CSV and Parquet through a job, with size and decompression limits. CSV formulas are neutralised on export.
   - Single writer per table: an advisory lock on the dataset id, and a retry on a DuckLake conflict.
   - One write path for every lake write. Each commit emits `platform.data.snapshot.committed.v1` (tenant, dataset id, snapshot id).
   - The API never writes to the lakehouse.
   - New credential scope `data:write` for uploads and dataset creation. New action kind `data.write`.
   - Contract change: `{id}` in the data routes becomes the registry dataset id. The 016 `<schema>.<table>` routes are replaced.
3. Maintenance.
   - A maintenance job on the scheduler: flush inlined data, merge files, expire snapshots, clean up files, under the same lock.
   - Protected snapshots (named in receipts) are kept for the replay window.
   - Lakehouse retention per tenant.
4. Erasure and backups.
   - Erasure flow: delete rows, force expiry and cleanup, and record which receipts can no longer be replayed.
   - Backups runbook: `pg_dump -Fc` of `rag_platform` and `lakehouse`, plus the SeaweedFS bucket, as one set.
5. Seed load and Data page.
   - Load the reference company into the lakehouse.
   - Data page: datasets, schema, snapshots, governed preview, "query as of" a snapshot.

## Out of scope
- Contracts and breaking schema changes (021). Pipelines and connectors (018). Grants and masking (023, 024).
- An upload form in the UI. Uploads are an API call in this sprint.

## Nav placement
Data > Datasets.

## Questions this sprint closes
- Q27 and Q35 (retention of `jobs`, `outbox`, `processed_events`, raw files, `sandbox_events`, `run_tokens`), if the scheduler work allows. Otherwise they move to 018, and the report says so.

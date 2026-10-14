# Sprint 017: Threat model
## Assets
- Lakehouse tables, snapshots and files; raw uploads.
- The writer S3 keys.
- Receipts that name snapshots (replay).

## Trust boundaries crossed
- Caller upload to the API, then the object store, then the worker.
- Worker to DuckLake (read-write) and SeaweedFS.
- Exported CSV to a spreadsheet on the user's machine.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Two writers race on one table and one job aborts or loses rows. | Tampering | Advisory lock per dataset; retry on conflict. | `test_lake_writer_lock.py`. |
| T2 | An oversized or highly compressed upload exhausts disk or memory. | Denial of service | Byte, row and decompressed limits, checked while streaming and from Parquet metadata. | `test_lake_upload_limits.py::test_zip_bomb_refused`, `::test_row_limit`. |
| T3 | Erasure misses a copy (old snapshot, inlined rows, raw file). | Information disclosure | Forced expiry of every holding snapshot, cleanup now, raw object deleted, catalog checked. | `test_lake_erasure.py`. |
| T4 | A receipt claims a replay that is no longer possible, silently. | Repudiation | `lake_erasures.unreplayable_decisions` lists them. | `test_lake_erasure.py::test_unreplayable_decisions_recorded`. |
| T5 | Maintenance expires a snapshot that a receipt needs. | Repudiation | Protected set from `data.read` decisions inside the replay window. | `test_lake_maintenance.py::test_protected_snapshot_survives`. |
| T6 | An exported CSV runs a formula in a spreadsheet. | Elevation of privilege | Formula neutralising on export. | `test_csv_export_neutralised.py`. |
| T7 | The API process writes to the lakehouse or holds writer keys. | Elevation of privilege | Read-only attach and read keys in the API; writer keys only in workers. | `test_data_write_routes.py::test_api_has_no_writer_credentials`. |
| T8 | A non-additive schema change rewrites history. | Tampering | Refused with `schema_change_refused` until contracts (021). | `test_lake_schema_versions.py::test_type_change_refused`. |

## Abuse cases
- A user uploads a CSV with `=HYPERLINK(...)` cells. The stored value is unchanged; the export neutralises it.
- A user with `data:write` tries to erase rows. Erasure needs `admin`; the deny is recorded.

## OWASP items in scope
- LLM02 2026 (sensitive information disclosure): erasure is complete across copies.
- LLM10 2026 (unbounded consumption): upload limits.
- ASI items: none directly. Agents do not write to the lakehouse.

## Residual risks
- Backups taken before an erasure still hold the rows until they rotate. The runbook says so.
- Deleting the raw upload on erasure is a delete of a hash-addressed file. Strict rule 6 says raw files are never changed; this needs a recorded decision.

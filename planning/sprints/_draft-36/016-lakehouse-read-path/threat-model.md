# Sprint 016: Threat model
## Assets
- Each tenant's lakehouse tables and files.
- The catalog role password and the per-tenant S3 keys.
- The decision chain (snapshot ids).

## Trust boundaries crossed
- Caller to the data routes (credential, tenant).
- The API process to DuckDB, to the `lakehouse` database and to SeaweedFS.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A read reaches another tenant's metadata schema. | Information disclosure | Only the caller's catalog is attached; `ATTACH` is refused after the lock. | `test_lake_isolation.py::test_other_schema_denied`, `::test_attach_refused`. |
| T2 | A read reaches another tenant's files by path. | Information disclosure | `allowed_directories` is the tenant prefix; S3 identity limited to that prefix. | `::test_read_parquet_other_prefix_denied` (local and in `ducklake.sh`). |
| T3 | Data leaves through DuckDB (`COPY TO`, http functions). | Information disclosure | `enable_external_access=false`; read-only attach. | `::test_copy_to_refused`, `::test_http_read_refused`. |
| T4 | Configuration is changed or an extension is loaded at query time. | Elevation of privilege | No autoinstall or autoload, unsigned refused, `lock_configuration=true`. | `test_lake_lock.py::test_set_refused`, `::test_install_refused`. |
| T5 | A table name from the URL is used as SQL. | Tampering | `{id}` must match the catalog's table list; identifiers quoted. | `test_data_routes.py::test_injection_in_id_is_404`. |
| T6 | Catalog or S3 secrets reach logs, errors or agents. | Information disclosure | Secrets as `SecretStr`, from a file; errors mapped to codes; no secret in any port type. | `test_lake_lock.py::test_error_text_has_no_secret`; import-lint test. |
| T7 | A slow query blocks the API. | Denial of service | Thread pool, timeout with `interrupt()`, `memory_limit`, `threads`. | `test_lake_event_loop.py`; `::test_timeout_gives_504`. |
| T8 | A read cannot be tied to the data it saw. | Repudiation | Snapshot pinned and in the decision hash. | `test_lake_snapshot_record.py`. |

## Abuse cases
- An analyst of tenant A guesses `t_b.invoices` as a dataset id. The answer is 404 `dataset_not_found`, and a deny row is written in tenant A.
- A future agent tries `SELECT * FROM read_csv('/etc/passwd')`. External access is off.

## OWASP items in scope
- ASI03 (identity and privilege abuse): tenant from the credential only, per-tenant catalog and keys.
- LLM02 2026 (sensitive information disclosure): no cross-tenant reads, secrets kept out of model context.
- ASI06 (memory and context poisoning): none yet. Agents do not read data until 027.

## Residual risks
- One catalog role can reach every metadata schema at the Postgres level. Isolation rests on the attach and the lock. A role per tenant is a later option.
- DuckLake on Postgres is new. The lock order is proved by a spike and by `test_lake_lock.py`, not by a long track record.

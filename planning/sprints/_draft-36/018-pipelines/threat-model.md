# Sprint 018: Threat model

## Assets
- Source credentials (`refco_reader` password, HTTP tokens), held as env or file secrets.
- The internal network: Postgres, Valkey, SeaweedFS, the cloud metadata address.
- Tenant datasets written by pipeline loads.
- The job queue and the scheduler (shared by every tenant).

## Trust boundaries crossed
- A tenant's pipeline definition (tenant input) becomes a worker job (platform process).
- The HTTP connector crosses from the compose network to an external host.
- The Postgres connector crosses into the source database.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | HTTP source URL points at an internal service or metadata address (SSRF) | Information disclosure | `adapters/egress.py`: allowlist, deny private and reserved ranges and compose names, connect to the checked IP, no redirects | `test_egress.py::test_ssrf_corpus_denied` |
| T2 | DNS rebinding: name is public at check time, private at connect time | Information disclosure | Resolve once, connect to that IP, Host header kept | `test_egress.py::test_rebinding_uses_checked_ip` |
| T3 | Credentials stored in `source_config` or echoed in a task log | Information disclosure | Credential-like keys refused; secrets resolved only in the worker; logs carry codes, not values | `test_pipelines_api.py::test_inline_secret_refused`, `test_pipelines_api.py::test_no_secret_in_logs` |
| T4 | Tenant A runs or reads tenant B's pipeline | Elevation of privilege | RLS on all four tables; tenant from the credential; 404 for foreign ids | `test_pipelines_tenancy.py::test_foreign_pipeline_404` |
| T5 | A load writes to another tenant's dataset | Tampering | `target_dataset_id` checked under `tenant_connection`; write path attaches only the job's tenant catalog | `test_pipelines_tenancy.py::test_foreign_target_refused` |
| T6 | Postgres connector writes to the source | Tampering | Role with SELECT only, read-only transaction | `test_source_connector.py::test_postgres_read_only` |
| T7 | Schedule flood or huge backfill starves the queue | Denial of service | `PIPELINE_BACKFILL_MAX`; overlap skip; minimum cron interval of one minute | `test_backfill.py::test_backfill_limit`, `test_scheduler_overlap.py` |
| T8 | Oversized or slow HTTP response | Denial of service | `PIPELINE_HTTP_MAX_BYTES`, timeout | `test_egress.py::test_size_and_timeout_limits` |
| T9 | Purge deletes rows still needed (unsent outbox, active run token) | Tampering | Purge functions only touch sent, finished, expired or revoked rows | `test_retention_platform.py::test_live_rows_kept` |
| T10 | A pipeline change leaves no trace | Repudiation | Every route writes a decision record through `enforce()` | `test_pipelines_api.py::test_changes_recorded` |

## Abuse cases
- A producer sets the HTTP source to `http://169.254.169.254/latest/meta-data/`. Denied, task fails with `egress_denied`.
- A producer sets the source URL to `http://valkey:6379/`. Denied as a compose name.
- A producer asks for a backfill of 10,000 partitions. Refused with 422.

## OWASP items in scope
- OWASP Top 10:2025 A01 Broken Access Control (includes SSRF): T1, T2, T4.
- ASI02 Tool Misuse: not yet. No agent calls pipelines in this sprint. The connectors are built so a later agent tool cannot widen egress.
- LLM Top 10: none. No model is called.

## Residual risks
- An allowlisted external host can still serve harmful content. Content is typed and size-limited, never executed.
- Retention defaults are placeholders until the owner answers Q27 and Q35.

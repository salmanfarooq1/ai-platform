# Sprint 018: Pipelines. Requirements

Vertical slice, module M4 Data Plane (with Kernel scheduler work). Contract first, then backend, then UI, then e2e.

## Scope
1. **Pipeline definitions.** Tenant-scoped tables for pipelines, runs and tasks.
   - A pipeline has a source, a target dataset, a cron schedule (optional) and parameters.
   - Each run and each task inside it keeps its status, times, row count and error code.
2. **Source connectors.** Each one sits behind a new `SourceConnector` port.
   - Postgres: reads the reference source database (`refco_source`) with a read-only role.
   - Files: CSV and Parquet from the object store, through the existing `ObjectStore` port.
   - HTTP: an egress allowlist. Private ranges, loopback, link-local and compose service names are denied (SSRF).
   - Source credentials come from env or file secrets only, by reference. Never from a table or a request body.
3. **Generalised scheduler.** `workers/scheduler.py` today only queues retention purges on an interval loop, and `core/database/jobs.py` hard-codes `USER_KINDS`.
   - Cron schedules for any job kind. A job kind registry replaces the hard-coded tuple.
   - A run is skipped, and recorded as skipped, while the previous run of the same schedule is still queued or running.
   - Backfill: one run per partition parameter.
4. **Retention jobs** (Q27, Q35) for `jobs`, `outbox`, `processed_events`, raw files in the object store, `sandbox_events` and `run_tokens`. Skip this item if Sprint 017's report says it is done.
5. **Pipelines page** (Data > Pipelines): definitions, runs, task logs, run now, backfill.
   - Run duration and dataset freshness are exported as metrics, ready for Sprint 044.
   - ADR-0016: pipelines on the job queue, dbt as the transform layer.

## Out of scope
- dbt transforms (019). CDC and Kafka consumers (020). Lineage events (025).
- Free-form SQL in a pipeline. Writing to any target other than a registered dataset.
- An external orchestrator (Dagster, Airflow).

## Nav placement
Data > Pipelines.

## Questions this sprint closes
- Q27: retention of `jobs`, `outbox`, `processed_events` and raw files (unless 017 closed it).
- Q35: retention of `sandbox_events` and `run_tokens` (unless 017 closed it).

# Sprint 022: Connectors, pipelines and transforms. Requirements

Data pillar (M4). Bring in the data we must hold, using existing open-source connectors, and land it through one governed write path. Then transform it with dbt, and optionally follow client change streams. This is a two-part sprint: part a covers items 1–4, part b covers items 5–7.

Source: old 017, old 018, old 019, old 020, plus new scope (integration-data-connectors research note).

## Scope
1. **Dataset registry and write path** (from old 017).
   - Tables `datasets`, `dataset_tables` and `dataset_schema_versions` with RLS. Additive schema changes are automatic. Other changes are refused until contracts exist (023).
   - Single writer per table: an advisory lock on the dataset id, with retry on a DuckLake conflict. The API never writes. Writes run only in workers.
   - Each commit emits `platform.data.snapshot.committed.v1`. New scope `data:write` and action `data.write`.
   - Every pipeline names why the data is held (rule 12), for example "history", "documents" or "client asked for a copy".
2. **Maintenance, erasure and backups** (from old 017).
   - A maintenance job (flush, merge, expire, clean up) under the same lock. Snapshots named in receipts are protected for the replay window.
   - Erasure flow records which receipts can no longer be replayed.
   - Backups go into the 015 `poc backup` set: `pg_dump -Fc` of both databases plus the bucket, as one set.
3. **Connectors through dlt** (Apache-2.0 core only; premium sources are not used).
   - A `SourceConnector` port with a dlt adapter. Sources: files and Excel, SQL databases (Postgres, MySQL, SQL Server), REST APIs, and two SaaS verified sources (HubSpot and one accounting API, picked in the blueprint).
   - HTTP and SaaS calls go through an egress allowlist. Private ranges, loopback, link-local and compose names are denied (SSRF).
   - Credentials are by reference only, from secret files. Never from a table or a request body.
   - dlt writes to a staging area. Our write path commits into DuckLake. dlt never writes the lakehouse directly.
4. **Pipelines and scheduler** (from old 018).
   - Tables for pipelines, runs and tasks. Cron schedules for any job kind through a job kind registry (replacing the hard-coded `USER_KINDS`). Overlapping runs are skipped and recorded. Backfill by partition.
   - Retention jobs (Q27, Q35) for `jobs`, `outbox`, `processed_events`, raw files, `sandbox_events` and `run_tokens`.
   - Data > Pipelines page. Run duration and freshness exported as metrics. ADR-0016.
5. **dbt transforms** (from old 019).
   - `dbt-core==1.12.5` with `dbt-duckdb==1.11.0` runs as a `dbt_run` job, as a worker subprocess.
   - Generated projects only: no user SQL, macros or Python models. Typed template parameters. Vendored packages, with `dbt deps` offline.
   - Short-lived generated profiles. Incremental models take the writer lock.
   - The OpenLineage dbt spike goes through the `LineageEmitter` port, spooled until 025. `DO_NOT_TRACK=1`.
6. **Client streams and CDC** (optional profile `streams`; from old 020).
   - Two inputs: the client's own Kafka topics (SASL, ACLs, our consumer group), and CDC from a client Postgres through Debezium Server or Kafka Connect (`quay.io/debezium/connect:3.6.2.Final`, port 8083 never published, secrets through a config provider).
   - Our sink keeps the old 020 design:
     - micro-batches, dedupe by key, and a guard by source LSN
     - offsets stored in the same DuckLake transaction
     - deletes, and the initial snapshot from `op=r` events
     - an added column becomes an add; any other schema change quarantines the batch
     - the tenant comes from the registration, never from the message
   - The CDC source setup is documented for the client's DBA: replication-only role, filtered publication, heartbeat and a WAL growth alert.
   - Freshness is measured from the source commit time. Q41 (first real Kafka consumer) is closed by this sink. ADR-0017.
7. **Verify scripts.** `scripts/verify/dlt.sh`, `dbt.sh` and `cdc.sh`, plus fakes for pytest (a fake source and a fake CDC event stream).

## Out of scope
- Contracts and breaking schema changes (023). Grants and masking (024). The lineage store (025).
- User-written dbt code, or a dbt sandbox. An external orchestrator (Dagster, Airflow).
- The Airbyte platform and connectors (ELv2, not OSI). Writing our own connector where a dlt or Debezium one exists.
- Kafka TLS between our own services (SASL only, as before).
- Changed from old 017–020:
  - Connectors are dlt instead of hand-written.
  - CDC and Kafka are an optional profile.
  - Client Kafka topics are a new input.
  - Backups join the `poc` lifecycle.

## Nav placement
- Data > Datasets: snapshots and "query as of".
- Data > Pipelines: definitions, runs, task logs, run now, backfill.
- Data > Streams: the client topics and CDC sources, with a freshness badge.

## Questions this sprint closes
- Q27 and Q35 (retention of jobs, outbox, processed events, raw files, sandbox events, run tokens).
- Q41 (first real Kafka consumer).
- Q43, Q44 and Q45 for stream topics, decided in the blueprint as in old 020.

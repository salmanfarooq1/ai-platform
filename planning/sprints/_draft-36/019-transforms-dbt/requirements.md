# Sprint 019: Transforms with dbt. Requirements

Vertical slice, module M4 Data Plane. Transform steps on top of the Sprint 018 pipelines.

## Scope
1. **dbt as a job.** `dbt-core==1.12.5` with `dbt-duckdb==1.11.0` runs as a `dbt_run` job against the tenant's DuckLake catalog.
   - It runs in a worker, as a subprocess, with only the job's tenant catalog attached.
2. **Generated per-tenant projects.** A project is generated for each run from the pipeline definition and platform templates.
   - No user-written SQL, macros or Python models in this program step. They would need the sandbox.
   - Template parameters are typed and validated before generation.
3. **Packages and profiles.**
   - Packages come only from a vendored allowlist. `dbt deps` runs offline.
   - `profiles.yml` is generated per run with short-lived secrets and deleted after the run. Secrets are never stored.
4. **Incremental models.** Merge-style incremental models take the single-writer lock (advisory lock on the dataset id, retry on conflict).
5. **OpenLineage spike.** Prove whether `openlineage-dbt==1.53.0` works with dbt-duckdb on DuckLake.
   - Lineage events go through the `LineageEmitter` port either way. Until 025 the no-op adapter spools them in `lineage_raw_events` (owned by M5).
   - dbt writes go through Sprint 017's write path and emit `platform.data.snapshot.committed.v1`.
   - `DO_NOT_TRACK=1` and dbt anonymous usage stats off.

## Out of scope
- User-written dbt code of any kind. A dbt sandbox.
- The lineage store and graph (025). MetricFlow (026). dbt tests as quality checks (022).

## Nav placement
Data > Pipelines: transform steps shown on the pipeline detail and run timeline.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. The spike answers whether `openlineage-dbt` is usable here.

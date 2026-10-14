# Sprint 019: Acceptance
- [ ] **A1.** All checks in the builder brief pass. Test delta stated against Sprint 018's report. `check_skips.py` passes with the allowlist. The licence gate passes with dbt in the lock file. Evidence: `evidence/pytest-full.txt`, `evidence/check_skips.txt`, `evidence/licences.txt`.
- [ ] **A2.** The reference finance marts (`stg_invoices`, `stg_ledger`, `fin_revenue_by_region_month`) build from the finance pipeline. Each mart has a new snapshot. Evidence: `evidence/finance-marts.txt`.
- [ ] **A3.** A second run after new source rows is incremental: `run_results.json` reports the merge, only the new month rows change, and the row count matches the source. Evidence: `evidence/incremental.txt`.
- [ ] **A4.** A package outside `packages.lock`, or one whose hash differs, fails the run before dbt starts, with `package_not_allowed`. Evidence: `evidence/packages.txt`.
- [ ] **A5.** No secret value appears in any stored row, task log, temp file left behind, `manifest.json`, `run_results.json` or `dbt.log`. The test scans for the actual secret values. Evidence: `evidence/no-secrets.txt`.
- [ ] **A6.** Two transform runs on the same mart at once both finish; the lock serialises them. Evidence: `evidence/writer-lock.txt`.
- [ ] **A7.** Spike result recorded: does `openlineage-dbt` emit events on dbt-duckdb with DuckLake? Raw events reach the no-op emitter's spool through `LineageEmitter` for the finance run either way (`test_lineage_goes_through_emitter`). The finance run emits `platform.data.snapshot.committed.v1` per target (`test_dbt_run_emits_snapshot_committed`). Evidence: `evidence/openlineage-spike.md`, `evidence/lineage-raw.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** No new service. The worker's `docker stats` line during a dbt run is recorded. Evidence: `evidence/memory.txt`.

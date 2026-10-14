# Sprint 016: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 015's report. `check_skips` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** Cross-tenant negative tests are all denied: other schema, other path, `read_parquet('s3://<bucket>/<other prefix>/...')`, `ATTACH`, `COPY ... TO`, `INSTALL`, `SET`, and another tenant's dataset through the API (404, same body as unknown). Evidence: `evidence/isolation.txt`.
- [ ] **A3.** Settings cannot be changed after the lock (`SET memory_limit`, `SET enable_external_access=true`, `RESET`). Evidence: `evidence/lock.txt`.
- [ ] **A4.** Every preview's decision row has `extensions.data.snapshot_id`, and the rows returned are those of that snapshot. `DataAccess.current_snapshot` returns one catalog-wide id, and the contract suite passes on the real and no-op adapters. Evidence: `evidence/snapshot-record.txt`.
- [ ] **A5.** The event loop is not blocked: heartbeat lag stays under 50 ms while a slow read runs. Evidence: `evidence/event-loop.txt`.
- [ ] **A6.** `scripts/verify/ducklake.sh` passes on SeaweedFS. Evidence: `evidence/ducklake-live.txt`.
- [ ] **A7.** Playwright: Data > Datasets lists tables and shows a preview with its snapshot id. Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats --no-stream` for the API under a preview load, with `DUCKDB_MEMORY_LIMIT` stated. Evidence: `evidence/memory.txt`.

# Sprint 018: Acceptance
- [ ] **A1.** All checks in the builder brief pass. Test delta stated against Sprint 017's report. `check_skips.py` passes with the allowlist. Evidence: `evidence/pytest-full.txt`, `evidence/check_skips.txt`, `evidence/ui-checks.txt`.
- [ ] **A2.** The reference finance pipeline (Postgres source, `refco_reader`) loads on its cron schedule. A new snapshot appears on the target dataset, one `platform.data.snapshot.committed.v1` is emitted for it (`test_pipeline_load_emits_snapshot_committed`), and the run is `succeeded`. Evidence: `evidence/finance-pipeline.txt` (test output of `test_reference_finance_pipeline_on_schedule`).
- [ ] **A3.** Every SSRF case in the egress corpus is denied before any connection: private IPv4 and IPv6, loopback, link-local (`169.254.169.254`), compose names (`postgres`, `valkey`), a DNS name that resolves to a private address, and a redirect to one. Evidence: `evidence/ssrf.txt`.
- [ ] **A4.** A schedule that fires while its previous run is still running records a `skipped` run with `skip_reason=overlap` and queues no job. Evidence: `evidence/overlap.txt`.
- [ ] **A5.** A backfill of three partitions creates three runs. Each writes its own partition. The dataset shows the three loads. Evidence: `evidence/backfill.txt`.
- [ ] **A6.** The purge job removes expired rows from the six tables named in scope (or the report says 017 did it). The app role still has no DELETE on them. Evidence: `evidence/retention.txt`.
- [ ] **A7.** Pipelines page: create, run now, see task logs, backfill (Playwright). No secret value appears in any API response or task log. Evidence: `evidence/playwright.txt`, `evidence/no-secrets.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** No new compose service. The `docker stats` line for the worker during the finance load is recorded. Evidence: `evidence/memory.txt`.

# Sprint 020: Acceptance
- [ ] **A1.** All checks in the builder brief pass. Test delta stated against Sprint 019's report. `check_skips.py` passes with the allowlist. `docker compose --profile cdc config` is valid. Evidence: `evidence/pytest-full.txt`, `evidence/check_skips.txt`, `evidence/compose-cdc-config.txt`.
- [ ] **A2.** Edits made by the reference change generator appear in the lakehouse: inserts, updates and deletes, with freshness from `ts_ms`. Each applied batch emits one `platform.data.snapshot.committed.v1` per table (`test_cdc_batch_emits_snapshot_committed`). Live in `scripts/verify/cdc.sh`, fake in pytest. Evidence: `evidence/cdc-live.txt`, `evidence/cdc-apply.txt`.
- [ ] **A3.** The sink is killed between the data write and the Kafka commit, then restarted. No change is applied twice and none is lost (row counts and checksums match the source). Evidence: `evidence/cdc-replay.txt`.
- [ ] **A4.** An added source column appears as a new nullable column. A narrowed type quarantines the batch and pauses only that table. Evidence: `evidence/cdc-schema.txt`.
- [ ] **A5.** A message on tenant A's topic that names tenant B's database is quarantined, and tenant B's datasets are unchanged. Evidence: `evidence/cdc-tenancy.txt`.
- [ ] **A6.** No credential is visible through any API, log, Connect REST response or `docker inspect` env. Port 8083 is not published. A Kafka client without SCRAM credentials, or with the sink's user writing to `cdc.`, is refused. Evidence: `evidence/cdc-secrets.txt`, `evidence/kafka-acl.txt`.
- [ ] **A7.** The freshness badge shows on Data > Datasets and turns amber when stale (Playwright). Evidence: `evidence/playwright.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats` lines for `kafka`, `debezium` and `cdc-sink` under the change generator. Evidence: `evidence/memory.txt`.

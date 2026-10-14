# Sprint 012: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 011's report. `scripts/check_skips.py` passes with the updated allowlist. Evidence: `evidence/checks.txt`, `evidence/pytest-int-e2e.xml`.
- [ ] **A2.** The cache contract suite is green on `valkey/valkey-bundle:9.1.3`, locally and in CI. Evidence: `evidence/cache-contract-valkey.txt`, `evidence/valkey-spike.txt`.
- [ ] **A3.** The Kafka suite is green on `apache/kafka:4.3.1` through `scripts/verify/kafka.sh`. Evidence: `evidence/kafka-live.txt`.
- [ ] **A4.** The S3 contract suite and the presigned URL test are green on SeaweedFS live through `scripts/verify/seaweedfs.sh`. Evidence: `evidence/seaweedfs-live.txt`.
- [ ] **A5.** `docker compose config` is valid for the default set and for each profile (`models`, `cdc`, `lake`, `observability`). Evidence: `evidence/compose-config.txt`.
- [ ] **A6.** No published port is bound to `0.0.0.0` (test and `docker compose ps` output). Evidence: `evidence/ports.txt`.
- [ ] **A7.** `scripts/preflight.sh` passes on the build machine and fails on a stubbed bad engine. Evidence: `evidence/preflight.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats --no-stream` lines for `valkey`, `kafka`, `seaweedfs` and `ollama`. Evidence: `evidence/memory.txt`.

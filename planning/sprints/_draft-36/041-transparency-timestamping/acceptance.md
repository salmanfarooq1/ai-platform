# Sprint 041: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 040's numbers. `check_skips.py` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** An inclusion proof for a receipt and a consistency proof between two checkpoints verify offline with `scripts/verify/receipt.py`. A changed leaf or root fails. Evidence: `evidence/proofs.txt`.
- [ ] **A3.** A scheduled run stamps a chain head and a checkpoint. The token verifies offline against the TSA certificate chain. Evidence: `evidence/timestamps.txt`.
- [ ] **A4.** With no anchor settings, `GET /v1/transparency/status` shows `external_anchor: none` and a warning. No network call leaves the compose network (egress guard test). Evidence: `evidence/anchor-default.txt`.
- [ ] **A5.** A clock skewed past `CLOCK_MAX_DRIFT_MS` makes the stamp job refuse with `clock_drift`, health shows it, and an allowed call still succeeds. Evidence: `evidence/clock.txt`.
- [ ] **A6.** UPDATE and DELETE on the log tables fail, even as the owner role. Evidence: `evidence/append-only.txt`.
- [ ] **A7.** `scripts/verify/tsa.sh` passes on the live TSA, or is marked "not verified here" with the reason. The backup drill restores keys and log on a copy and an old receipt still verifies. Evidence: `evidence/tsa-live.txt`, `evidence/backup-drill.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats` line for `timestamp-server`. Evidence: `evidence/memory.txt`.

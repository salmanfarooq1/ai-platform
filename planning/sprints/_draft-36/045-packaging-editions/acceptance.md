# Sprint 045: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 044's numbers. `check_skips.py` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** Each wheel holds only its own packages; `dist/SHA256SUMS` matches the files. Evidence: `evidence/wheels.txt`.
- [ ] **A3.** Each of Gateway, Assurance, Agents, Data and Full installs from wheels in a clean container with no repo source and passes its smoke set. Data also passes with the `models` profile off (`test_data_edition_without_models`). Evidence: `evidence/editions.txt`.
- [ ] **A4.** In the Gateway edition, every Data and Agents route answers `module_disabled`, and an enabled-but-missing module stops the start. Evidence: `evidence/module-boundaries.txt`.
- [ ] **A5.** The release SBOM lists Python, npm, image and model components (with `models.lock` digests). The licence report passes, and fails on a seeded non-OSI fixture. Evidence: `evidence/sbom.txt`, `evidence/licence-report.txt`.
- [ ] **A6.** `scripts/verify/restore.sh` restores on a copy: chain, receipt, pack, log consistency and a snapshot read all verify. Evidence: `evidence/restore.txt`.
- [ ] **A7.** The release workflow runs on a test tag in a fork or with `workflow_dispatch` and blocks on a failing edition. Evidence: `evidence/release-gate.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats` for each edition's default profile set at idle. Evidence: `evidence/memory.txt`.

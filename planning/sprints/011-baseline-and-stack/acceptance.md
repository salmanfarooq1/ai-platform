# Sprint 011: Acceptance

## Part a
- [ ] **A1.** All checks pass. The counts match the baseline (1568 backend passed plus the new tests, 10 skipped, 207 Vitest, 82 Playwright). `scripts/check_skips.py` passes with the allowlist file. Evidence: `evidence/checks-a.txt`, `evidence/pytest-int-e2e-a.xml`.
- [ ] **A2.** The two mode tests in `tests/unit/test_config_mode.py` pass with a `.env.local` present that sets other values, and `test_real_env_beats_env_local` passes. Evidence: `evidence/config-mode.txt`.
- [ ] **A3.** `test_docs_links.py` passes with `docs/learning_docs/` present and git-ignored. Evidence: `evidence/docs-links.txt`.
- [ ] **A4.** The licence gate passes on the real tree and fails on the seeded non-OSI fixture. Evidence: `evidence/licence-gate.txt`.
- [ ] **A5.** The SBOM files for Python and npm are produced and valid CycloneDX JSON. Evidence: `evidence/sbom.txt` (component counts and spec version).
- [ ] **A6.** The gitleaks CLI is clean over the full history, and the image scan has no unaccepted critical finding. Evidence: `evidence/gitleaks.txt`, `evidence/image-scan.txt`.
- [ ] **A7.** Every image in compose, the workflows and the `Dockerfile` is pinned by digest. Poetry is 2.3.3 in CI and `mcp` is `2.2.0` in the lock. No pin is younger than two weeks without a noted security reason. Evidence: `evidence/pins.txt`, including a grep that finds no image without `@sha256:`.
- [ ] **A8.** The LiteLLM licence and incident check is recorded with sources, and is either clear or raised as a blocker. Evidence: `evidence/litellm-check.md`.

## Part b
- [ ] **B1.** All checks pass, with the test delta stated against part a. `scripts/check_skips.py` passes with the updated allowlist (SeaweedFS entry). Evidence: `evidence/checks-b.txt`, `evidence/pytest-int-e2e-b.xml`.
- [ ] **B2.** The cache contract suite is green on `valkey/valkey-bundle`, locally and in CI. Evidence: `evidence/cache-contract-valkey.txt`, `evidence/valkey-spike.txt`.
- [ ] **B3.** The Kafka suite is green on `apache/kafka:4.3.1` through `scripts/verify/kafka.sh`, and the default compose set starts with no Kafka. Evidence: `evidence/kafka-live.txt`.
- [ ] **B4.** The S3 contract suite and the presigned URL test are green on live SeaweedFS through `scripts/verify/seaweedfs.sh`. Evidence: `evidence/seaweedfs-live.txt`.
- [ ] **B5.** `docker compose config` is valid for the default set and for each profile (`models`, `streams`, `lake`, `observability`). Evidence: `evidence/compose-config.txt`.
- [ ] **B6.** No published port is bound to `0.0.0.0` (test and `docker compose ps` output). Evidence: `evidence/ports.txt`.
- [ ] **B7.** `scripts/preflight.sh` passes on the build machine and fails on a stubbed bad engine. Evidence: `evidence/preflight.txt`.
- [ ] **B8.** The docs name the keyword leg correctly. A grep finds no "BM25" claim outside the compatibility notes and the API values. Evidence: `evidence/keyword-naming.txt`.

## Both parts
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats --no-stream` lines for `valkey`, `kafka`, `seaweedfs` and `ollama`. Evidence: `evidence/memory.txt`.

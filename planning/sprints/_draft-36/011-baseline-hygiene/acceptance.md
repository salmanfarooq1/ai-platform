# Sprint 011: Acceptance
- [ ] **A1.** All checks pass with the same counts as the baseline: 1568 backend passed plus the new tests, 10 skipped, 207 Vitest, 82 Playwright. `scripts/check_skips.py` passes with the allowlist file. Evidence: `evidence/checks.txt`, `evidence/pytest-int-e2e.xml`.
- [ ] **A2.** The two mode tests in `tests/unit/test_config_mode.py` pass with a `.env.local` present that sets other values, and `test_real_env_beats_env_local` passes. Evidence: `evidence/config-mode.txt`.
- [ ] **A3.** `test_docs_links.py` passes with `docs/learning_docs/` present and git-ignored. Evidence: `evidence/docs-links.txt`.
- [ ] **A4.** The licence gate passes on the real tree and fails on the seeded non-OSI fixture. Evidence: `evidence/licence-gate.txt`.
- [ ] **A5.** The SBOM files for Python and npm are produced and valid CycloneDX JSON. Evidence: `evidence/sbom.txt` (component counts and spec version).
- [ ] **A6.** The gitleaks CLI is clean over the full history, and the image scan has no unaccepted critical finding. Evidence: `evidence/gitleaks.txt`, `evidence/image-scan.txt`.
- [ ] **A7.** Every image in compose, the workflows and the `Dockerfile` is pinned by digest, Poetry is 2.3.3 in CI and `mcp` is `2.2.0` in the lock. Evidence: `evidence/pins.txt` (a grep that finds no image without `@sha256:`).
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

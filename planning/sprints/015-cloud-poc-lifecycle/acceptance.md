# Sprint 015: Acceptance

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

- [ ] **A1. Local release manifest.** Images are pinned by digest. The local manifest identifies local build images. Unresolved placeholders and digest mismatches are refused. Evidence: `evidence/release-manifest.txt`.
- [ ] **A2. Wheelhouse.** The app image installs dependencies with `pip install --no-index --find-links`. Evidence: `evidence/wheelhouse.txt`.
- [ ] **A3. Local commands.** `up`, `backup`, `down` and `status` use the local host through `Runner`; no cloud or SSH target is accepted. Evidence: `evidence/poc-commands.txt`.
- [ ] **A4. Maintenance and backup.** During capture, non-health requests receive 503 before `enforce()` and create no decision row. Workers and relays pause. Maintenance on/off changes are recorded. The backup manifest binds its captured set, and failures end maintenance. Evidence: `evidence/backup.txt`.
- [ ] **A5. Real restore drill.** The Architect-run local drill restores row counts, chain heads, an old receipt and the signing-key id. Evidence: captured command output in `evidence/drill.txt`.
- [ ] **A-sec.** Threat-model tests pass. Evidence: `evidence/threat-tests.txt`.

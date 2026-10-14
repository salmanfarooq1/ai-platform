# Sprint 046: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 045's numbers. `check_skips.py` passes with the allowlist. Evidence: `evidence/checks.txt`.
- [ ] **A2.** A fresh clone in a clean WSL distribution or container runs `scripts/showcase/all.sh` with only the commands in `docs/getting-started.md`. Evidence: `evidence/fresh-clone.txt`.
- [ ] **A3.** Each of `m0.sh`, `ma.sh`, `mb.sh` (Full edition), `mc1.sh`, `mc2.sh`, `md.sh` and `me.sh` passes with `SHOWCASE_MODEL=fake`; `m0.sh` and `mb.sh` also pass with `SHOWCASE_MODEL=local` (or are marked "not verified here" with the reason). Evidence: `evidence/journeys.txt`.
- [ ] **A4.** Every journey has a Playwright spec, and all pass. Evidence: `evidence/e2e.txt`.
- [ ] **A5.** The landing and How it works pages tell the full chain; `copy-check` maps every claim to a may-claim item with a test. Evidence: `evidence/copy-check.txt`.
- [ ] **A6.** README, getting started, architecture and the ADR index (to ADR-0031) are updated; the docs link test passes. Evidence: `evidence/docs.txt`.
- [ ] **A7.** `STATE.md` and `ROADMAP.md` close program 2 and list program 3 follow-ups (a governed SQL endpoint for external BI tools, Trino, Dagster, hosting). Evidence: `evidence/planning.txt` (diff stat).
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** `docker stats` per journey's profile set at its peak. Peak memory stays inside the 12 GB WSL limit for `mc1.sh` and `mc2.sh` (`test_showcase_mc_profiles_split`). Evidence: `evidence/memory.txt`.

# Sprint 046: Showcase walkthrough. Requirements

Docs and end-to-end tests, all modules. Closes milestone ME and program 2.

## Scope
1. One scripted walkthrough per milestone on the reference company.
   - `scripts/showcase/m0.sh` (from Sprint 015, refreshed), `ma.sh`, `mb.sh`, `mc1.sh`, `mc2.sh`, `md.sh`, `me.sh`.
   - MC is split in two to fit memory: `mc1.sh` (core, models, identity, policy) and `mc2.sh` (core, lake, models, guard).
   - The MB journey needs the Full edition.
   - Each script runs its milestone journey from `planning/program/sprint-map.md` with the personas' keys, prints each step and its evidence, and exits non-zero on the first failed step.
   - `scripts/showcase/all.sh` runs them in order and switches compose profiles between journeys.
2. Playwright coverage for every journey.
   - One spec per milestone in `ui/e2e/showcase-*.spec.ts`, on the real API with fakes, as the existing e2e tests run.
3. Landing page and How it works page tell the full chain.
   - Source row, pipeline, product and contract, grant and purpose, sandboxed agent, gateway decision, signed receipt, log and timestamp, evidence pack.
   - Every new claim maps to a may-claim item in `docs/design/CONTENT_STYLE.md` backed by a test. `npm run copy-check` passes.
4. Final docs pass.
   - `README.md`, `docs/getting-started.md` for a fresh laptop (Docker Engine, profiles, model pull, first walkthrough), `docs/architecture.md`, and the ADR index up to ADR-0031.
5. Close program 2.
   - `planning/STATE.md` and `planning/ROADMAP.md` closed for program 2.
   - Follow-ups for program 3: a governed SQL endpoint for external BI tools, Trino, Dagster, hosting.

## Out of scope
- New features or new controls. A gap found by a journey is fixed only if it is a bug in built scope; otherwise it goes to `planning/QUESTIONS.md`.
- Hosted deployment (program 3).
- Renaming the in-app Walkthrough page (`/app/walkthrough`).

## Nav placement
No new console page. Public pages: landing and How it works.

## Questions this sprint closes
- None. Open questions left at the end of program 2 are listed in `planning/STATE.md` with an owner.

# Sprint 032: Release and trust. Requirements

Platform (all modules). Each edition installs and runs on its own. The release is signed, accessible and ready for an air-gapped site. A small vendor can answer a buyer's security questionnaire with evidence. One scripted walkthrough covers every milestone. Tag `v1.0.0`. This is a two-part sprint: part a covers items 1–4, part b covers items 5–8.

Source: old 045, old 046, plus new scope (enterprise-gaps-how research note, bundle D).

Depends on: 031.

## Scope
1. **Per-module packages and edition installs.**
   - One wheel per module: kernel, gateway (with the evidence core), evidence, agents, data plane, lineage, insights. Modules register through the entry point group `platform.modules`. Inter-wheel versions are pinned exactly.
   - Editions (Gateway, Assurance, Agents, Data, Full) install from wheels on a clean machine, through Compose and through the 031 Helm chart.
   - The edition smoke matrix, run from wheels, is a required release gate.
2. **Release SBOM and licence report.**
   - One CycloneDX release SBOM (wheels, npm build, images, models from `models.lock`) and a licence report. The gate fails on any non-OSI licence in the default stack.
3. **Air-gap bundle.**
   - An offline install bundle: images by digest, the wheelhouse, model weights with `models.lock`, the Helm chart and an image-mirror script.
   - `poc up` works from the bundle with no internet. A test proves it.
4. **Accessibility.**
   - `@axe-core/playwright` (MPL-2.0) runs in e2e with WCAG 2.2 AA tags, and every page passes.
   - A manual pass covers what automation cannot. An ACR is published from the ITI VPAT template, stating that automated checks do not prove conformance.
5. **Vendor trust package.**
   - CAIQ v4 answers, pre-filled from the plan and evidence.
   - `security.txt`, a short vulnerability disclosure policy and a patch SLA in `SECURITY.md`.
   - A SOC 2 readiness map (controls to evidence). No SOC 2 report, which needs an auditor.
6. **Exit and portability runbook.**
   - Export everything in open formats: Parquet plus a catalog dump, a Postgres dump, configs, receipts with the verifier, and a key handover.
   - A tested restore on a fresh install. This answers DORA-style exit questions.
7. **Showcase walkthrough.**
   - One script per milestone (`scripts/showcase/m0.sh`, `mg.sh`, `md.sh`, `ma.sh`, `me.sh`) on the reference company. Each prints each step and its evidence and exits non-zero on the first failed step.
   - `all.sh` runs them in order, on a local machine or the 031 cloud VM.
   - One Playwright spec per milestone. The landing and How-it-works pages tell the full chain, with every claim backed by a test (`npm run copy-check`).
8. **Close program 2.**
   - Final docs pass: `README.md`, `docs/getting-started.md` (local and cloud), `docs/architecture.md`, and the ADR index up to ADR-0034.
   - `STATE.md` and `ROADMAP.md` closed. Program 3 follow-ups listed (for example, a governed SQL endpoint if the 029 spike passed, and native warehouse adapters).

## Out of scope
- Publishing wheels or images to a public index. A SOC 2 audit. FIPS 140-3.
- New features or controls. A gap found by a journey is fixed only if it is a bug in built scope; otherwise it goes to `planning/QUESTIONS.md`.
- Changed from old 045 and 046: Helm installs, the air-gap bundle, accessibility, the trust package and the exit runbook are new. Image signing with SBOM attestation and the gateway surface pen test moved to 018. The journeys follow the new milestones.

## Nav placement
- No new pages. The ACR and the trust package are documents.
- Platform > About shows the version, edition and SBOM link.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Pen-test findings that are accepted are logged there.

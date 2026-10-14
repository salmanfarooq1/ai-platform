# Sprint 046: Builder brief
You are the Builder for Sprint 046 in /home/ubuntu/ai-platform, on branch `sprint/046-showcase-walkthrough`. Docs and end-to-end tests across all modules. This sprint closes milestone ME and program 2. Work autonomously. Stop conditions are in AGENTS.md. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, `planning/ROADMAP.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- Sprint 045's `report.md`. `planning/program/sprint-map.md` (milestone journeys). `docs/showcase.md` and `scripts/showcase/m0.sh` (Sprint 015).
- `ui/src/landing/`, `docs/design/CONTENT_STYLE.md`, `.claude/skills/governed-design/SKILL.md`.

## Build
Everything in the blueprint. Order: scripts per milestone and `all.sh`, Playwright specs, CI job, landing and How it works, docs pass, planning close-out. Fix only bugs in built scope that a journey exposes; log each fix in `build-log.md` with its test.

## Tests
- Baseline: the numbers in Sprint 045's report.
- Scripts and specs use the reference company and the e2e fakes. The local-model run is extra evidence, never the gate.
- Each acceptance item and each threat row has a named test.

## Notes from the Architect
- **Names:** the scripts are "showcase" scripts. The in-app page `/app/walkthrough` keeps its name and content.
- **Profiles:** never start every profile at once. `all.sh` stops one journey's profiles before the next starts. Record peak memory per journey. Split `mc.sh` into `mc1.sh` (core, models, identity, policy) and `mc2.sh` (core, lake, models, guard); delete `mc.sh` and update `all.sh`. Run `mb.sh` on the Full edition.
- **Fresh clone (A2):** use a new WSL distribution or a clean container with Docker Engine. Follow `docs/getting-started.md` word for word, and fix the doc where it is wrong.
- **Claims:** a may-claim item needs a built feature and a named test. If a journey step is not fully built, the landing page does not claim it.
- **Program 3 follow-ups:** a governed SQL endpoint for external BI tools, Trino, Dagster, hosting, plus open items from `planning/QUESTIONS.md` and the residual risks in the packs (signed release artifacts, encrypted backups, external anchors on by default).
- **Migration:** none. Say so in the report.

## Run
If Postgres, Valkey or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run pytest -m unit -q --junitxml=planning/sprints/046-showcase-walkthrough/evidence/junit-unit.xml
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/046-showcase-walkthrough/evidence/junit.xml
poetry run python scripts/check_skips.py planning/sprints/046-showcase-walkthrough/evidence/junit.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python scripts/compliance/check_mappings.py --junit planning/sprints/046-showcase-walkthrough/evidence/junit-unit.xml --junit planning/sprints/046-showcase-walkthrough/evidence/junit.xml
shellcheck scripts/showcase/*.sh
SHOWCASE_MODEL=fake scripts/showcase/all.sh
SHOWCASE_MODEL=local scripts/showcase/m0.sh && SHOWCASE_MODEL=local scripts/showcase/mb.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`. Also run the release gate scripts from Sprint 045: `scripts/release/build_wheels.sh`, `scripts/release/install_edition.sh <edition>` for each edition, `scripts/supply_chain/sbom.sh --release` and `poetry run python scripts/release/licence_report.py`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names for the platform, no model or tool attribution.
- Short, simple sentences in docs and page copy.

## Finish
Write `report.md` and `evidence/`. The report has: the acceptance table with evidence links, test numbers and the delta against Sprint 045 and against the program 2 baseline (1568 backend passed, 10 skipped; 207 Vitest; 82 Playwright), "no migration", bugs fixed, deviations, open questions, memory per journey, and proposed commit blocks per `planning/program/branching-and-commits.md` (code fixes, tests, UI, ops, docs, planning). No commits by the Builder.

**Milestone ME (human actions, after QA signs off and the pull request merges):**
- Add a `CHANGELOG.md` section for `v1.0.0` with the test delta since `v0.44.0`, the migrations added since then (none expected), new services and measured memory. The Builder drafts it in the report.
- Run the release workflow from Sprint 045 on the tag.
- Proposed tag, run by a human on `main`: `git tag -a v1.0.0 -m "ME Packaging"` then `git push origin v1.0.0`.

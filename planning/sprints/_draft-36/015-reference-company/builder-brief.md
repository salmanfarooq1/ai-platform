# Sprint 015: Builder brief
You are the Builder for Sprint 015 in /home/ubuntu/ai-platform, on branch `sprint/015-reference-company`. Data and docs, Kernel: a fictional distributor, its generators, a source database, personas and the M0 showcase. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `planning/program/sprint-map.md` (milestone journeys) and the Sprint 014 report.
- `scripts/admin/identity.py`, `scripts/e2e/serve.py`, `ui/playwright.config.ts`, `gateway/policy.py` (`PolicyDocument`), `docker-compose.yml`.

## Build
Order: generators, dictionary and checksums; deny-list scan; source database and loader; change generator; personas; `m0.sh`; `serve.py --seed`; Playwright; docs. Write a short plan in `build-log.md` first.

## Tests
- **Baseline:** the numbers in Sprint 014's report.
- Unit tests generate the small size into `tmp_path`. The medium size runs only in `evidence/determinism.txt`, not in pytest.
- The integration test loads `refco_source` into a throwaway database on the test Postgres, not the compose `refco-source` service.
- `m0.sh` runs against a local stack. Save its full output.

## Notes from the Architect
- **Code facts:**
  - Policies are per tenant: `identity.py set-policy <tenant> <file.json>` publishes one active policy for the whole tenant. There is no per-principal policy. So a persona file holds that persona's scopes plus the tenant policy its journey step publishes. Record this as a question in `planning/QUESTIONS.md` (principal-level policy is a later decision, see 031).
  - `identity.py create-key --scopes` accepts only the six scopes. The key is printed once.
  - `scripts/e2e/serve.py` builds a throwaway database and serves the app with fakes. Add `--seed reference-company` without changing its default seed, so existing Playwright tests stay as they are.
  - `FakeModelCatalog` (014) gives the fake model a digest, so the Playwright receipt has one.
  - `ENABLED_MODULES` (013) is read at startup, so `m0.sh` restarts the API for step 4.
  - `data/` already holds `compliance/` and git-ignored `objects/`. Keep generated output out of git (`data/reference-company/out/`).
- **No real names.** Functional names only: "Reference Distributor", "North region", "Product line A". No real brand, person, city-specific company or domain.
- **PDF bytes:** fix the creation date, producer and document id, or the hash changes every run.
- **Pins:** the PDF library and any faker-like helper (prefer none) pinned and licence-checked. Save in `evidence/pins.txt`.
- **No migration.** `refco_source` DDL is fixture SQL, exempted by exact path in `scripts/check_no_ddl.sh` with a comment.

## Run
```bash
poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/showcase data/reference-company
poetry run mypy
poetry run lint-imports
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/015-reference-company/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/015-reference-company/evidence/pytest-int-e2e.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
poetry run python data/reference-company/generate.py --size medium --seed 42 --out /tmp/refco-medium
docker compose --profile lake up -d refco-source && poetry run python data/reference-company/load_source.py --size small
scripts/showcase/setup_personas.sh && scripts/showcase/m0.sh
cd ui && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs. Persona keys only in `.showcase/keys.env`.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1 to A6, A-sec, A-mem) with links to `evidence/`
- test numbers and the delta against Sprint 014's report
- "No migration"
- deviations and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md`: code (`data/reference-company/`, `feat(core)`), tests (`tests/`, `test(core)`), UI (`ui/e2e/showcase-m0.spec.ts`, `test(ui)`), ops (`docker-compose.yml`, `scripts/showcase/`, `scripts/e2e/serve.py`, `scripts/check_no_ddl.sh`, `chore(ops)`), docs (`docs/showcase.md`, `docs(ops)`), planning (`docs(planning)`), each with its `git add` paths, then the push and `gh pr create --base main` commands.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.

**Milestone M0 (human actions, after QA signs off and the pull request merges):**
- Add a `CHANGELOG.md` section for `v0.15.0` with the test delta since Sprint 010, the migrations added in Sprints 011 to 015, new services and measured memory. The Builder drafts it in the report.
- Proposed tag, run by a human on `main`: `git tag -a v0.15.0 -m "M0 Foundations"` then `git push origin v0.15.0`.

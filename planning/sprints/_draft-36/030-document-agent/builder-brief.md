# Sprint 030: Builder brief
You are the Builder for Sprint 030 in `/home/ubuntu/ai-platform`, on branch `sprint/030-document-agent`. This is a vertical slice: contract, backend, extraction agent, UI and an e2e test. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, and this folder (all five files).
- The reports of Sprints 015 (documents and generators), 017 (write path), 021 (contracts) and 027 (taint, tool capabilities, sandbox data runs).
- `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
Everything in the blueprint, in this order: contract, migration, pre-fetch job and `models.lock` entries, parse job, extraction agent and tools, review routes and publish, UI, the malicious-PDF fixture script, the accuracy script.

## Tests
- **Baseline:** the numbers in Sprint 029's report. State the delta.
- Write one test per acceptance item and per threat-model row, using the names given there.
- Pytest uses the fake sandbox and the fake model. Scripted plans read the pages and return fields. For the malicious PDF, the fake model follows the hidden instruction, so the test proves the controls rather than the model's good behaviour.
- **Parse in pytest:**
  - Run Docling on a two-page fixture with the network guard on.
  - If the weights volume is not available in CI, CI runs the `docling-models` init job first. Do not skip.
- The full reference set runs in `scripts/verify/docling.sh`. Add no new skips.

## Notes from the Architect
- **Pins:** `docling==2.130.0`. Record each weight file's source and licence in `evidence/pins.txt` and in `models.lock`. Use Apache-2.0 weights only. The TableFormer weights are dual-tagged CDLA-Permissive-2.0 and Apache-2.0: accept them under Apache-2.0 and record that in `models.lock` and the ADR-0009 append. If that is not possible, turn table structure off and record it. Any other weight that is not Apache-2.0 fails the gate: stop on that item and log it.
- **OCR engine:** use the OCR backend that Docling 2.130.0 ships by default, if its licence passes. Record which one.
- **No write tool:** the agent returns fields as its run result. The worker stores them. Do not give the agent a tool that writes, even to the queue.
- **Taint is from 027.** Reuse the `taint` stage and the capability tags. Do not add a second mechanism.
- **Publish:** add `submit_write(principal, dataset_id, rows_ref)` to the `DataAccess` port and call it. The real adapter queues the 017 job kind under its lock. M3 code must not import 017 internals; `lint-imports` checks it. Do not write to DuckLake from the API.
- **Action map:** register `document.review` with the `agents` module.
- **Memory:** Docling uses about 2 to 3 GB while parsing. Run it with the `models` profile only, and measure.
- **Migration:** use the next free number after Sprint 029's head.
- **Milestone MB:** this sprint closes MB. Run the MB journey from `planning/program/sprint-map.md` on the reference company with `scripts/showcase/mb.sh`. If no earlier sprint wrote it, write it here (`scripts/showcase/<milestone>.sh` in `planning/program/conventions.md`), and save the output in `evidence/mb-journey.txt`. Sprint 046 refreshes it.
- **Docs:** `docs/architecture.md`, `docs/operations.md`, ADR-0009 (append), the API docs, OpenAPI snapshot, `.env.example`, CHANGELOG (with the test delta), STATE.

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`. For the weights, run `docker compose --profile models up docling-models`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
poetry run pytest -q -rs --junitxml=planning/sprints/030-document-agent/evidence/pytest.xml
poetry run python scripts/check_skips.py planning/sprints/030-document-agent/evidence/pytest.xml
poetry run python scripts/eval/documents/accuracy.py --out planning/sprints/030-document-agent/evidence/extraction-accuracy.json
scripts/verify/docling.sh
scripts/showcase/mb.sh
poetry run python scripts/update_openapi.py
scripts/supply_chain/licence_gate.sh
scripts/models/check_lock.sh
scripts/ci/edition_smoke.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`.

Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names, no model or tool attribution. Use simple sentences in docs.

## Finish
Write `report.md` with:
- the acceptance table with evidence links
- the test numbers and the delta against Sprint 029
- the migration number
- the accuracy figures, memory and volume size
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(documents): add extraction and review contract`
- `feat(db): add document extraction review table`
- `feat(documents): parse offline and extract into contract-shaped reviews`
- `test(documents): contain the malicious pdf and check citations`
- `feat(ui): add document review queue with citation boxes`
- `chore(ops): pre-fetch document models into a volume`
- `docs(documents): describe the document path and model volume`
- `docs(planning): update state and changelog for the document agent`

The Builder does not commit. A human runs the commands.

**Milestone MB (human actions, after QA signs off and the pull request merges):**
- Add a `CHANGELOG.md` section for `v0.30.0` with the test delta since `v0.25.0`, the migrations added in Sprints 026 to 030, new services and measured memory. The Builder drafts it in the report.
- Proposed tag, run by a human on `main`: `git tag -a v0.30.0 -m "MB Agents and insights on data"` then `git push origin v0.30.0`.

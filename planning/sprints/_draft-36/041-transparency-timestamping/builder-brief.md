# Sprint 041: Builder brief
You are the Builder for Sprint 041 in /home/ubuntu/ai-platform, on branch `sprint/041-transparency-timestamping`. Infrastructure, module M2, with no new page. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md`, `threat-model.md`.
- Sprint 040's `report.md`, ADR-0012 and ADR-0029.
- `evidence/` (receipts, chain and keys after 040), `scripts/verify/receipt.py`, the generalised scheduler in `workers/`, `scripts/preflight.sh`.

## Build
Everything in the blueprint, in this order: ports and contract, migration, `evidence/translog.py`, the TSA and anchor adapters, the `timestamp_heads` job, the routes, verifier v2 subcommands, compose profile `trust`, docs. If the TSA image cannot be pulled here, build behind the port, keep `tsa.sh`, and mark A7 "not verified here".

## Tests
- Baseline: the numbers in Sprint 040's report (backend passed and skipped, Vitest, Playwright).
- The fake TSA and the live TSA pass one contract suite. pytest uses only the fake. The live run is `scripts/verify/tsa.sh`, never a skipped pytest.
- Name a test for every acceptance item and every threat row.

## Notes from the Architect
- **Pins:** re-check `ghcr.io/sigstore/timestamp-server` (at least `v2.0.6` for GHSA-xm5m-wgh2-rrg3; `stack.md` lists `v2.1.0` with an unverified date). Pin by digest. `rfc3161-client==1.0.9`. Save both in `evidence/pins.txt`.
- **SDK placement:** `rfc3161-client` and any HTTP client for anchors are imported only in `adapters/`. Add them to the import lint list and to the import-linter contracts.
- **Hashing:** leaf hash = SHA-256(0x00 || data), node = SHA-256(0x01 || left || right). Copy the proof checks into the verifier on purpose; a parity test keeps them in step.
- **Keys:** three keys since 040: receipt, checkpoint, TSA. Never sign a checkpoint with the receipt key. Keys come from files, never from the repo or logs.
- **The decision path stays as it is.** No new work inside the decision transaction. Appending a receipt happens on first issue, outside it.
- **Migrations:** the next free number after Sprint 040's head. Forward only, tested from the previous head.
- **No platform imports in the verifier.** It must run on a machine with only Python and `cryptography`.

## Run
If Postgres, Valkey or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then start the core stores with `docker compose up -d`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run python scripts/update_openapi.py
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/041-transparency-timestamping/evidence/junit.xml
poetry run python scripts/check_skips.py planning/sprints/041-transparency-timestamping/evidence/junit.xml
scripts/ci/edition_smoke.sh
scripts/supply_chain/licence_gate.sh
docker compose --profile trust config >/dev/null
scripts/verify/tsa.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names for the platform, no model or tool attribution.
- Short, simple sentences in docs.

## Finish
Write `report.md` and `evidence/`. The report has: the acceptance table with evidence links, test numbers and the delta against Sprint 040, the migration number, deviations, open questions, measured memory, and proposed commit blocks per `planning/program/branching-and-commits.md` (contract, migration, code, tests, UI, ops, docs, planning). No commits by the Builder. Update `planning/STATE.md`, `CHANGELOG.md` and close Q29.

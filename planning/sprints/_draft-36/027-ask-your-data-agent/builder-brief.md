# Sprint 027: Builder brief
You are the Builder for Sprint 027 in `/home/ubuntu/ai-platform`, on branch `sprint/027-ask-your-data-agent`. This is a vertical slice: contract, backend, sandbox agent, UI, evals and an e2e test. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, and this folder (all five files).
- `planning/program/vision-and-architecture.md` (target request path), ADR-0009 and ADR-0012.
- The reports of Sprints 009, 024, 025 and 026, and `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
Everything in the blueprint, in this order: contract, migration, tool capabilities and the taint stage, server-side tools, `sandbox_agent/data_agent.py`, output strip on the answer step, receipts and replay, UI, evals and workflows.

## Tests
- **Baseline:** the numbers in Sprint 026's report. State the delta.
- Write one test per acceptance item and per threat-model row, using the names given there.
- The PR tier uses the fake model with scripted tool plans per question, so it is deterministic.
- The nightly tier and the red team run outside pytest. Save their outputs to `evidence/`.
- The live sandbox checks go in `scripts/verify/openshell.sh`, never in a skipped pytest. Add no new skips.

## Notes from the Architect
- **Code fact (Q34):** `sandbox_agent/entry.py` is a retrieve-then-answer program, not the LangGraph agent. Keep it for knowledge-base runs. The data agent is a new module in `sandbox_agent/`. It must not import `litellm`, `langchain_litellm`, `asyncpg`, `duckdb` or `openshell`. Extend the import-lint test.
- **Code fact:** `KNOWN_TOOLS` in `gateway/policy.py` must list the four new tools, or `set-policy` refuses them.
- **Code fact:** `eval_runs` (migration 0009) has no `tenant_id` and no signature today. It stays platform-level.
- **Q40 wording:** Q40 in `planning/QUESTIONS.md` asks about cost display, not accuracy. Do not decide the cost part here. Add the accuracy threshold under Q40 as a second part: propose it from the measured nightly run, write it in `scripts/eval/data_agent/baseline.json`, and leave it for the owner to agree.
- **Pins:**
  - garak and PyRIT are UNV in `stack.md`. Pick releases at least two weeks old, check their licences against the gate, and record them in `evidence/pins.txt`.
  - The nightly model is `qwen3:4b-instruct-2507-q4_K_M` from `models.lock`, at temperature 0.
  - Telemetry is off for both tools.
- **Sandbox image:** record its size before and after adding LangGraph.
- **Keep it narrow:** no new tool may have `sends_out` or `writes` in production code. `send_report` exists only in tests.
- **Migration:** use the next free number after Sprint 026's head.
- **Docs:** ADR-0009 (append), `docs/architecture.md`, `docs/operations.md`, red-team runbook, OpenAPI snapshot, `.env.example`, CHANGELOG (with the test delta), STATE, QUESTIONS (Q34, Q40).

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/027-ask-your-data-agent/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/027-ask-your-data-agent/evidence/pytest-int-e2e.xml   # expected count from tests/skip_allowlist.json
scripts/supply_chain/licence_gate.sh   # garak and PyRIT must pass
scripts/models/check_lock.sh
scripts/ci/edition_smoke.sh
poetry run python scripts/eval/run_gate.py
poetry run python scripts/eval/data_agent/run_tier.py --tier pr
poetry run python scripts/update_openapi.py
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Also run:
- `run_tier.py --tier nightly` once, with the `models` profile.
- `scripts/verify/openshell.sh` where a Linux host allows it.

Script names come from `planning/program/conventions.md`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names, no model or tool attribution. Use simple sentences in docs.

## Finish
Write `report.md` with:
- the acceptance table with evidence links
- the test numbers and the delta against Sprint 026
- the migration number
- the measured accuracy and the proposed threshold
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(agents): add ask-data contract and tool capabilities`
- `feat(db): sign eval runs and record their tier`
- `feat(agents): run the data agent in the sandbox with taint and answer receipts`
- `test(agents): cover taint, output stripping, replay and leakage`
- `feat(ui): add ask-data answers with provenance and replay`
- `ci(agents): add nightly model and red-team eval tiers`
- `docs(adr): record the sandboxed data agent`
- `docs(planning): update state, questions and changelog for the data agent`


The Builder does not commit or tag.

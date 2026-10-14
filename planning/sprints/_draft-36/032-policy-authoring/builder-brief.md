# Sprint 032: Builder brief
You are the Builder for Sprint 032 in `/home/ubuntu/ai-platform`, on branch `sprint/032-policy-authoring`. This is a vertical slice: contract, backend, UI and e2e tests across both. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, and this folder (all five files).
- The reports of Sprints 021 (contracts), 027 (agent tools) and 031 (policy seam, inputs, bundles, replay script). ADR-0022.
- The AuthZEN Authorization API 1.0 final specification, and its published interop scenarios.
- `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
Everything in the blueprint, in this order: contract, migration, the rule compiler and must-never shape, AuthZEN routes, drafts and the test bench, the what-if job, the publish gate, the replay route and CLI, UI.

## Tests
- **Baseline:** the numbers in Sprint 031's report. State the delta.
- Write one test per acceptance item and per threat-model row, using the names given there.
- The AuthZEN interop vectors are vendored in `tests/fixtures/authzen/`, with their source URL and version in a README. Map their subjects and resources onto reference-company fixtures in one mapping file.
- Both engines run every new decision-table row: the Python engine directly, and OPA through `opa eval`. No live verify script is new; re-run `scripts/verify/opa.sh`. Add no new skips.

## Notes from the Architect
- **API path rule (rule 9):**
  - AuthZEN evaluation routes go under `/v1/authzen/...`.
  - The AuthZEN discovery document goes at `/.well-known/authzen-configuration`. Rule 9 in `planning/program/vision-and-architecture.md` allows public, read-only discovery documents under `/.well-known/`. Confirm the exact path in the AuthZEN 1.0 text; if it differs, follow the spec and say so in the report.
  - This sprint is the first to use rule 9. Record the decision in `planning/DECISIONS.md` and in `docs/architecture.md` (the route list next to `/` and `/health`). Sprints 033 and 037 reuse it.
  - Every other route stays under `/v1`.
- **AuthZEN is final at 1.0.** Label it "AuthZEN 1.0". Do not label any part "draft-compatible" here: that label is for 034.
- **ODCS field name:** confirm the agent-context field in the ODCS 3.2.0 schema before coding. If ODCS 3.2.0 has no such section, read the rules from `customProperties` with our schema, and say so in the report.
- **Scope:** drafts, evaluate, what-if and publish need `policy:write` (from 031).
- **Drafts:** use the same `PolicyDocument` validation as `set-policy`. A draft that fails validation is not stored.
- **Replay:** reuse `scripts/verify/replay_decision.py` from 031. Add `--explain` (rule ids from the Rego `rule_ids` output).
- **Migration:** use the next free number after Sprint 031's head.
- **Docs:** ADR-0022 (append), `planning/DECISIONS.md` (rule 9), `docs/architecture.md` (rule 9), `docs/api/`, `docs/contracts/policy/`, OpenAPI snapshot, `.env.example`, CHANGELOG (with the test delta), STATE.

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run pytest -q -rs --junitxml=planning/sprints/032-policy-authoring/evidence/pytest.xml
poetry run python scripts/check_skips.py planning/sprints/032-policy-authoring/evidence/pytest.xml
scripts/verify/opa.sh
poetry run python scripts/update_openapi.py
scripts/supply_chain/licence_gate.sh
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
- the test numbers and the delta against Sprint 031
- the migration number
- the AuthZEN discovery path served, and the rule 9 entries in `DECISIONS.md` and `docs/architecture.md`
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(policy): add authzen, draft, what-if and replay contracts`
- `feat(db): add policy drafts and what-if runs`
- `feat(policy): compile contract must-never rules and run what-if over recorded inputs`
- `test(policy): cover authzen interop, drafts, what-if and replay`
- `feat(ui): add policy test bench, what-if and decision replay`
- `docs(adr): record policy authoring and authzen mapping`
- `docs(planning): update state and changelog for policy authoring`

The Builder does not commit. A human runs the commands.

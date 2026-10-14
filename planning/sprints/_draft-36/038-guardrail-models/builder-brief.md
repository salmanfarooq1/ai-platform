# Sprint 038: Builder brief
You are the Builder for Sprint 038 in /home/ubuntu/ai-platform, on branch `sprint/038-guardrail-models`. This is a vertical slice: port, service, gateway stages, policy data, measurement, UI. Work autonomously. Stop conditions are in `AGENTS.md`: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `gateway/guardrails.py`, `api/services/guardrails.py`, `gateway/enforce.py`, the Sprint 027 breaker, the Sprint 031 Rego bundle and decision-table suite, `models.lock`, `planning/QUESTIONS.md` Q37.

## Build
Write `build-log.md` with a short plan first.
1. Pin check: Presidio `2.2.364`, the spaCy model and its version, `granite3-guardian:2b` digest. Save in `evidence/pins.txt`.
2. Port, fakes, contract suite.
3. `guard_service/` and its Dockerfile stage; the `guard` profile.
4. Adapters, registry, settings.
5. Gateway stages, `output.check`, policy fields in both engines, reason codes, record v2 `guard` extension.
6. Breaker rules into `data.trifecta`; decision-table rows; `opa test` cases.
7. Labelled set, `guard_eval.py`, thresholds, `scripts/verify/guard.sh`.
8. Q37 re-check. UI.

## Tests
- Baseline: the numbers in Sprint 037's report. State the delta.
- Fakes: `tests/fake_guard.py` in every pytest tier. CI never loads Presidio or the guard model.
- Live: `scripts/verify/guard.sh`, not a skipped pytest.
- Every test named in `threat-model.md`, and one named test per acceptance item.

## Notes from the Architect
- **Code fact.** Today's guardrails are pattern checks in `api/services/guardrails.py`, used by the `guardrails` stage, and the output check only flags low confidence. Keep both. The new stages come after them.
- **Thresholds and budgets are placeholders** until an owner confirms them: settings with defaults, and a question in `planning/QUESTIONS.md` (like Q26). Never present them as agreed rules. Defaults: PII recall 0.90 and precision 0.80 per entity type; guard recall 0.80 and precision 0.80 on the injection label. Budgets on CPU: PII 300 ms p95, guard model 3000 ms p95. Record the measured values next to them.
- **Masking happens before the text leaves the gateway path.** The record stores counts by entity type, never the value or its offset.
- **Separate service.** Presidio and spaCy stay out of the API image. The adapter talks HTTP to `guard_service` on the compose network, bound to no host port.
- **Code fact from Sprint 027.** The breaker is the `taint` stage, which runs after `grant`: `EnforcementContext.taint` is set by a tool result tagged `reads_untrusted`, and a `sends_out` or `writes` tool on a tainted run is denied with `tainted_run_tool_blocked`. Keep the stage and the reason. Move only its rule table into `data.trifecta`.
- **Both engines.** The Python engine and OPA must give the same answer for every new table row. Add `taint` and the trifecta flags to `PolicyInput`.
- **Memory.** Set `OLLAMA_MAX_LOADED_MODELS=3` in the `guard` profile only. Do not change it for other profiles.
- **No migration expected.** If one is needed, use the next free number after Sprint 037's head.

## Run
If the local stack is down: `docker compose up -d postgres valkey` (service names as of Sprint 012). Then run every line below and save the output in `evidence/`.
- `poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- `poetry run lint-imports`
- `poetry run pytest -m unit -q`, then `poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/038-guardrail-models/evidence/junit.xml`
- `poetry run python scripts/check_skips.py planning/sprints/038-guardrail-models/evidence/junit.xml` (the expected count comes from `tests/skip_allowlist.json`, Sprint 011)
- `scripts/supply_chain/licence_gate.sh` (the licence gate from Sprint 011)
- `scripts/models/check_lock.sh` (the `models.lock` check from Sprint 014; the guard model and spaCy model are in the lock)
- `scripts/ci/edition_smoke.sh` (all five editions, Sprint 013; CI runs it from `.github/workflows/editions.yml`)
- `opa test policy/ -v` (the pinned `opa` binary and the Rego bundle from Sprint 031)
- `poetry run python scripts/update_openapi.py` after any contract change, then the OpenAPI drift test.
- `cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e`. Never run `playwright install`.
- `docker compose --profile guard config` and `scripts/verify/guard.sh` (or record "not verified here").
- `poetry run python scripts/eval/guard_eval.py --fake` in CI mode.

## Rules
- Never weaken, skip or delete a test to get green. Say whether the code or the expectation was wrong.
- No secrets in files or logs. Refer to them by env var name.
- No commits or pushes. No "demo" wording. No brand names. No model or tool attribution in any file.
- Plain words and simple sentences in docs.

## Finish
- Every acceptance check has captured output in `evidence/`, under the file name `acceptance.md` gives.
- Update docs in lockstep: the ADR, `docs/`, `.env.example`, the OpenAPI snapshot, `planning/STATE.md`, `CHANGELOG.md` (test delta, migration, measured memory if any).
- Write `report.md`:
  - the acceptance table (check, result, evidence file)
  - test numbers against the baseline
  - deviations from the blueprint, and why
  - open questions (also in `planning/QUESTIONS.md`)
  - proposed commit blocks, in the order of `planning/program/branching-and-commits.md`, each with its `git add` paths and message
- Do not run `git commit` or `git push`. A human runs the blocks.
- Suggested blocks: `feat(guardrails)` port and contract; `feat(guardrails)` service, adapters, stages and policy data; `test(guardrails)` with the labelled set; `feat(ui)`; `chore(ops)` compose profile and verify script; `docs(adr)` ADR-0027; `docs(planning)` with the Q37 result.

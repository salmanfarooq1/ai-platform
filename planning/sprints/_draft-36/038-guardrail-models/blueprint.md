# Sprint 038: Blueprint

## Ports and adapters
- `ports/guard.py`: `PiiDetector.analyze(text, entities) -> list[Finding(entity, start, end, score)]` and `anonymize(text, rules) -> str`; `GuardModel.classify(text, risk) -> GuardVerdict(label, score, model, digest)`. Frozen dataclasses.
- `adapters/presidio_detector.py`: calls the `guard` service over the compose network. The Presidio and spaCy imports live only in `guard_service/` (a small HTTP service built from a Dockerfile stage, models baked in).
- `adapters/ollama_guard.py`: the guard model through the existing model adapter path, with its digest from `models.lock`.
- `tests/fake_guard.py`: a fake detector and a fake guard model. Both pass the contract suite (`tests/contracts/test_guard_contract.py`).
- Registry: `GUARD_PII=presidio|off`, `GUARD_MODEL=granite|off`. Settings validated in `core/settings.py`, with `GUARD_SERVICE_URL` and per-stage budgets `GUARD_PII_BUDGET_MS` (default 300), `GUARD_MODEL_BUDGET_MS` (default 3000). The budget defaults are placeholders with a logged question.

## Gateway
- New stages after `guardrails`: `pii` and `guard` (names from `planning/program/conventions.md`). They run on the input of every governed action. On output: a new action kind `output.check` (introduced here) through `enforce()` runs the same `pii` and `guard` stages on the text. Model and agent paths call it before returning text. The record says whether a stage ran on input or output.
- Policy fields: `pii: {entity_type: "mask"|"redact"|"block"}`, `guard: {risks: [..], block_above: float}`. In Rego data and in the Python engine.
- A stage that cannot run, or runs past its budget, denies with `guardrail_unavailable` (fail closed).
- Reason codes: `pii_blocked`, `guard_blocked`, `guardrail_unavailable`. Masking is not a deny: the text is changed and the record notes it.
- Record v2 extension `guard`: `{pii: {entity_type: count}, model, digest, verdict, score, latency_ms}`. No text, no matched values.

## Trifecta breaker
The Sprint 027 breaker reads `data.trifecta` (tool classes: `reads_private`, `reads_untrusted`, `sends_out`, `writes`) from the bundle. The Python engine reads the same JSON. The `taint` stage runs after `grant`, as in Sprint 027. `PolicyInput` (031) gains `taint: {tainted, sources}` and `trifecta: {reads_private, reads_untrusted, sends_out, writes}` (booleans, no text). The decision-table suite gains breaker rows that both engines pass: clean run, tainted run with a `sends_out` tool, tainted run with a `writes` tool, and all three trifecta flags set.

## Measurement
- `tests/data/guard/labelled.jsonl`: synthetic texts from the reference company, each with labels (PII entity spans; risk labels). The SHA-256 of the file goes into the eval record.
- `scripts/eval/guard_eval.py`: precision and recall per label, p50 and p95 latency per stage. Thresholds in `scripts/eval/guard_thresholds.json`, with placeholder defaults (PII recall 0.90 and precision 0.80 per entity type; guard recall 0.80 and precision 0.80 on the injection label) and a question in `planning/QUESTIONS.md`. They are not agreed rules. CI uses the fakes for the gate logic; the live numbers come from `scripts/verify/guard.sh`.
- Results are stored as signed eval records (Sprint 027).

## Compose and scripts
Profile `guard`: the `guard` service (built locally, pinned base by digest) and the guard model in Ollama. The `guard` profile sets `OLLAMA_MAX_LOADED_MODELS=3` (chat, embedding and guard model). Other profiles keep the default. `scripts/verify/guard.sh`: boot, pull check against `models.lock`, run the eval, print pass or fail, save a `docker stats` line.

## Q37 re-check
Run the Sprint 009 file-read probe against the pinned OpenShell. Record whether a refused read leaves an event, and with which kind. Save it in `evidence/q37-recheck.txt`.

## UI (follow `.claude/skills/governed-design/SKILL.md`)
Governance > Guardrails: read-only from policy, plus the last eval result and dataset hash. Decision detail shows the guard extension.

## Tests
- Contract suite on fakes and, in the verify script, on the live service.
- Unit: masking by entity type; budget overrun denies; no text in the extension.
- Integration: PII masked in a model answer; a blocked entity denies; the guard model blocks an injection sample; guard service down denies.
- Decision table: breaker rows on both engines; `opa test` covers them. `test_decision_table_taint_rows`, `test_taint_stage_after_grant`.
- Compose: `test_ollama_max_loaded_models_guard_only` (`docker compose config` sets it only with the `guard` profile).
- Playwright: Guardrails page and the guard verdict on a decision.

## Docs
ADR-0027 (guardrail models). `docs/configuration.md`, `docs/operations.md` (guard profile, budgets). `models.lock` updated if the spaCy model is listed there.

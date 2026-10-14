# Sprint 038: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against Sprint 037's report. `check_skips.py` passes with the allowlist. `opa test` passes. Evidence: `checks.txt`
- [ ] **A2.** Precision and recall on the labelled set meet the placeholder thresholds in `guard_thresholds.json` (question logged), and the dataset hash is recorded. Live run, or "not verified here" with the reason. Evidence: `guard-eval.txt`
- [ ] **A3.** p95 latency of each stage is within its placeholder budget on the CPU profile. Evidence: `guard-latency.txt`
- [ ] **A4.** A receipt for a guarded call shows the guard model digest and verdict, and no text. Evidence: `guard-receipt.txt`
- [ ] **A5.** PII in a model answer is masked per the policy's entity rules; a blocked entity gives `pii_blocked`. Evidence: `pii-masking.txt`
- [ ] **A6.** With the guard service stopped, calls deny with `guardrail_unavailable`. Evidence: `fail-closed.txt`
- [ ] **A7.** The trifecta breaker rows pass on both engines from policy data, with `taint` and the trifecta flags in `PolicyInput` (`test_decision_table_taint_rows`). Q37 re-check recorded. Evidence: `breaker-table.txt`, `q37-recheck.txt`
- [ ] **A-sec.** Every test in `threat-model.md` passes. Evidence: `threat-tests.txt`
- [ ] **A-mem.** `docker stats` lines for the `guard` service and Ollama with the guard model loaded. `OLLAMA_MAX_LOADED_MODELS=3` is set only in the `guard` profile (`test_ollama_max_loaded_models_guard_only`). Evidence: `docker-stats.txt`

## Notes
- Evidence is captured command output in `evidence/`, never hand-written.
- A check that needs a live service that cannot run here is marked "not verified here", with the verify script named and the reason.
- QA signs off `threat-model.md` before the sprint is accepted.

# Sprint 038: Guardrail models. Requirements

A vertical slice in M1 Gateway: a PII stage and a local guard model stage on input and output, measured on a labelled set, with the trifecta breaker moved into policy.

## Scope
1. **Presidio stage** (`presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364`).
   - Runs on input and on output.
   - The spaCy model is pre-fetched into the image. No download at runtime.
   - Masking by entity type, set in policy.
2. **Local guard model** `granite3-guardian:2b`, from `models.lock`, as a stage.
   - Its digest and its verdict go into the decision record (record v2 extension).
3. **Measurement.**
   - A labelled set for precision and recall, with thresholds. The dataset hash is recorded.
   - A latency budget per stage.
   - Thresholds and budgets are placeholders: settings with defaults and a question in `planning/QUESTIONS.md`, never agreed rules, until an owner confirms them.
4. **Policy-driven trifecta breaker.**
   - The Sprint 027 breaker reads its rules from OPA data (and the same data in the Python engine).
   - A fake detector for pytest. `scripts/verify/guard.sh` for the live services.
5. **Q37 re-check.** Does the pinned OpenShell log an event when it refuses a file read? Record the answer. ADR-0027.

## Out of scope
- Memory guardrails and autonomy tiers (Sprint 039).
- Hosted guard services. Everything runs locally.
- Training or tuning a guard model.

## Nav placement
Governance > Guardrails: stages on or off per tenant (from policy), masking by entity type, thresholds, the last measured precision, recall and latency.

## Questions this sprint closes
- Q37: closed with the re-check result, or carried with the evidence.

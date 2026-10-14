# Sprint 018: Policy engine and replay. Requirements

Gateway pillar, M1 policy seam and AuthZEN front, with evidence core extensions. A decision can be reproduced offline, and a draft policy can be tested before it goes live.

Source: old 031, old 032, plus new scope (gateway-proxy-and-agents research note, review.md).

## Scope
1. **OPA adapter** on the `PolicyEngine` seam.
   - Move the Protocol, `PolicyInput` and `PolicyVerdict` to `ports/policy.py` and re-export from `gateway/policy.py`. `PolicyInput` is frozen, built by the gateway and holds no free text (hashes, ids, scopes, boundary, `surface`).
   - `adapters/opa_policy.py` posts `{"input": ...}` to `/v1/data/platform/decision`. `OPA_TIMEOUT_MS` default 200. Any error, timeout, non-200 or missing result is a deny `policy_unavailable`.
   - OPA `openpolicyagent/opa:1.20.2-static` in compose profile `policy`. `POLICY_ENGINE=python|opa`, default `python`.
   - The Rego bundle is built and signed (`opa build --signing-key`). `bundle_sha256` is the manifest revision. Startup refuses a revision that differs from the expected hash.
2. **One decision-table suite** for both engines (`tests/policy/decision_table.yaml`).
   - It holds every tool-argument case, each persona, the Insights kinds, the new purpose cases and all three outcomes. `opa test` runs without a server.
   - Later sprints add rows with their fields: 019 taint flags, 020 delegation chain, 028 autonomy tier.
3. **Three outcomes** and the purpose stage.
   - `PolicyVerdict.outcome` is `allow`, `deny` or `approval_required`, with `rule_ids`. Until 019 an `approval_required` verdict is recorded and treated as a deny.
   - New stage `purpose` after `policy`, calling the engine with `check="purpose"`. A declared purpose must be in the policy's list for that action kind. Binding purpose to grants is 024.
4. **Replay data.**
   - Each decision stores the policy bundle hash and the input hash (record v2 extension `policy`). The canonical `PolicyInput` is stored with the decision for its retention period, so no other source is needed.
   - With both, `opa eval` reproduces the decision offline. The 017 verifier gains policy replay.
5. **AuthZEN Authorization API 1.0.**
   - `/access/v1/evaluation` and the batch endpoint, mapped onto the `enforce()` checks. The 016 `authorize()` service becomes conformant.
   - Public discovery path under `/.well-known/` (rule 9 is already recorded by 016). Interop tests against a reference client. Search APIs are out.
6. **Policy test bench and what-if** (Governance > Policies).
   - Write a draft tenant policy and run it against chosen inputs.
   - What-if: run a draft over the last N days of stored inputs and list the decisions that would change, before publishing. A publish stores the what-if summary.
   - New scope `policy:write` (today `admin`, which still satisfies it).
7. **Replay "why was this allowed"** in the UI and the CLI: the stored input, the bundle, the rule ids and the outcome, compared with the recorded outcome.
8. **First tenant policies** (Q8). The 014 personas get real tenant policies as tested fixtures.
9. **Tests.** `test_decision_table_python`, `test_decision_table_opa`, `test_decision_table_insights_kinds`, `test_opa_down_denies`, `test_bundle_revision_mismatch_refuses_start`, `test_unsigned_bundle_refused`, `test_policy_extension_in_record`, `test_offline_replay_matches`, `test_approval_required_is_deny`, `test_whatif_lists_changed_decisions`, `test_authzen_interop`, `test_policy_write_scope_known`. Contract suite on the Python engine and on OPA against a fake OPA server. ADR-0022.

## Out of scope
- Writing Rego in the browser. Drafts are tenant policy documents. The Rego bundle changes only through the repo and CI.
- Acting on `approval_required` (019). Guardrail rules in OPA data (019).
- AuthZEN search APIs and the access request profile (019, 024).
- Compiling contract "must never" rules into policy data (023). The data slot exists. This was in old 032 and moved.
- Trino's use of the bundle (021, 024).

## Nav placement
Governance > Policies: engine, bundle hash, persona policies, test bench, what-if. Evidence > Decisions: replay.

## Questions this sprint closes
- Q8: the first real tenant policies are the persona policies, written and tested here.
- Q15: the Policies page shows whether `blocked_terms` is set and how many terms, to `audit:read`. The terms are shown to `admin` only. The owner confirms in QUESTIONS.

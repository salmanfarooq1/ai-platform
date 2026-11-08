# Sprint 018: Policy engine and replay. Requirements

Gateway pillar, M1 policy seam and AuthZEN front, with evidence core extensions. A decision can be reproduced offline, and a draft policy can be tested before it goes live.

Source: old 031, old 032, plus new scope (gateway-proxy-and-agents research note, review.md).

Depends on: 017.

## Scope
1. **Versioned Python policy package.**
   - The policy engine is a small, pure, versioned package that the standalone verifier can import. Pin its package hash in each decision record.
   - Replay and what-if use this exact package. `PolicyInput` is built by the gateway and holds hashes, ids, scopes, boundary and `surface`, never free text.
2. **Decision table and purpose stage.**
   - Keep a decision table for tool arguments, each persona, Insights kinds, purpose cases and all three outcomes. Later sprints add 019 taint flags, 020 delegation chain and 028 autonomy tier.
   - Add the `purpose` stage after `policy`. A declared purpose must be in the policy's list for that action kind. Binding purpose to grants is 024.
3. **Three outcomes.**
   - `PolicyVerdict.outcome` is `allow`, `deny` or `approval_required`, with `rule_ids`. Until 019 an `approval_required` verdict is recorded and treated as a deny.
4. **Replay data.**
   - Each decision stores the policy package hash and input hash (record v2 extension `policy`). The canonical `PolicyInput` is stored with the decision for its retention period.
   - The 017 verifier replays the decision offline using the pinned package.
5. **AuthZEN Authorization API 1.0.**
   - `/access/v1/evaluation` and the batch endpoint, mapped onto the `enforce()` checks. The 016 `authorize()` service becomes conformant.
   - Public discovery path under `/.well-known/` (rule 9 is already recorded by 016). Interop tests against a reference client. Search APIs and the approval profile are out.
6. **Policy test bench and what-if** (Governance > Policies).
   - Write a draft tenant policy and run it against chosen inputs.
   - What-if: run a draft over the last N days of stored inputs and list the decisions that would change, before publishing. A publish stores the what-if summary.
   - New scope `policy:write` (today `admin`, which still satisfies it).
7. **Replay "why was this allowed"** in the UI and the CLI: the stored input, the pinned policy package, the rule ids and the outcome, compared with the recorded outcome.
8. **First tenant policies** (Q8). The 014 personas get real tenant policies as tested fixtures.
9. **MG close.** Sign container images with cosign and attach an SBOM attestation. Pen test the 016–020 surface and retain the result as evidence.
10. **Tests.** `test_decision_table_python`, `test_policy_package_hash_in_record`, `test_policy_extension_in_record`, `test_offline_replay_matches`, `test_approval_required_is_deny`, `test_whatif_lists_changed_decisions`, `test_authzen_interop`, `test_policy_write_scope_known`. ADR-0022.

## Out of scope
- Writing policy code in the browser. Drafts are tenant policy documents; the versioned policy package changes through the repo and CI.
- Acting on `approval_required` (019). Guardrail rules in policy data (019).
- OPA runtime adapter, Rego bundle and two-engine parity suite (030).
- AuthZEN search APIs and the approval profile (030); access request profile (024).
- Compiling contract "must never" rules into policy data (023). The data slot exists. This was in old 032 and moved.
- Trino's use of the bundle (021, 024).

## Nav placement
Governance > Policies: engine, package hash, persona policies, test bench, what-if. Evidence > Decisions: replay.

## Questions this sprint closes
- Q8: the first real tenant policies are the persona policies, written and tested here.
- Q15: the Policies page shows whether `blocked_terms` is set and how many terms, to `audit:read`. The terms are shown to `admin` only. The owner confirms in QUESTIONS.

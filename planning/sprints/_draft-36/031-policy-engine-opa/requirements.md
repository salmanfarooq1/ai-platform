# Sprint 031: Policy engine on OPA. Requirements

Vertical slice. Module: M1 Gateway (policy seam), with evidence core extensions.

## Scope
1. **OPA adapter** on the existing seam (`PolicyEngine` Protocol and `PythonPolicyEngine` in `gateway/policy.py`).
   - OPA runs as `openpolicyagent/opa:1.20.2-static`, a sidecar in compose profile `policy`.
   - The Python engine stays the default.
2. **One decision-table suite** that both engines must pass.
   - `opa test` runs on the Rego bundle in CI, with no server needed.
3. **Three outcomes:** allow, deny and approval required.
   - Until 034, "approval required" is recorded and treated as a deny.
4. **Purpose in policy, and the first tenant policies.**
   - Purpose moves into policy with no change in behaviour.
   - The reference company personas get real tenant policies as fixtures (Q8).
5. **Replay data.** Each decision stores two hashes (record v2 extension):
   - the policy bundle hash
   - the input document hash
   - With them, `opa eval` can reproduce any decision offline. ADR-0022.

## Out of scope
- Policy authoring, the test bench, what-if and replay in the UI (032).
- Acting on "approval required" (034).
- Guardrail rules in OPA data (038).

## Nav placement
Governance > Policies: the engine, the bundle hash and the persona policies (read-only).

## Questions this sprint closes
- **Q8:** the first real tenant policies are the reference persona policies, written and tested here.
- **Q15:** the Policies page shows whether `blocked_terms` is set and how many terms it has, to `audit:read`. The terms themselves are shown to `admin` only. The owner confirms this in QUESTIONS.

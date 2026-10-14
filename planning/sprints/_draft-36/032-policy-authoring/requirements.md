# Sprint 032: Policy authoring. Requirements

Vertical slice. Module: M1 Gateway (policy data, AuthZEN front, authoring), reading M4 contracts through ports.

## Scope
1. **Contract rules into policy.** ODCS 3.2 agent-context rules ("must never" rules and usage instructions) are compiled into policy data per product.
2. **AuthZEN Authorization API 1.0.**
   - Evaluation endpoint `/access/v1/evaluation`, plus batch evaluations.
   - Each call is mapped onto the `enforce()` checks.
   - Interop tests.
3. **Policy test bench in the UI.** Write a draft and run it against chosen inputs.
4. **What-if.** Run a draft policy over the last N days of recorded inputs. Show the decisions that would change, before publishing.
5. **Replay.** Replay "why was this allowed" for any decision, in the UI and the CLI.

## Out of scope
- Writing Rego in the browser. Drafts are tenant policy documents and product rule data. The Rego bundle changes only through the repo and CI.
- AuthZEN search APIs (subject, resource and action search) and the access request profile (034).
- Approval flows for publishing a policy beyond the what-if gate (034 reuses the approval model).

## Nav placement
- Governance > Policies: the test bench and what-if.
- Evidence > Decisions: replay.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Record any new ones there.

# Sprint 032: Threat model
## Assets
- Live tenant policies and product rule data.
- Draft policies and what-if results, which show how past decisions would change.
- Stored policy inputs (hashes only) and bundles.
- The AuthZEN endpoint as a decision oracle.

## Trust boundaries crossed
- Contract authors (producers) into policy data.
- Tenant admins into drafts and publish.
- External enforcement points (AuthZEN clients) into the gateway.
- Auditors into replay.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A draft policy affects live decisions | Elevation of privilege | Engines load only the active policy and the built bundle. Drafts live in their own table. | `test_draft_never_active` |
| T2 | A policy is published without anyone seeing its effect | Tampering | Publish needs a finished what-if for the same draft hash | `test_publish_requires_whatif` |
| T3 | Replay or what-if output exposes prompt text or arguments | Information disclosure | Inputs hold hashes and flags only (031). Responses are checked for text. | `test_replay_output_hashes_only` |
| T4 | AuthZEN is used to probe another tenant's principals | Information disclosure | The tenant comes from the credential. A foreign subject gives `false` with no detail. | `test_authzen_foreign_subject` |
| T5 | AuthZEN evaluation books budget or skips the record | Repudiation | `evaluate_only` skips rate, budget and cost, but still writes a decision row | `test_authzen_evaluation_recorded` |
| T6 | A contract author writes a vague rule that compiles to nothing | Tampering | Only the structured shape compiles. Free text is refused. | `test_unstructured_rule_refused` |
| T7 | Replay runs on the current bundle and hides a past mistake | Repudiation | Replay loads the recorded bundle by hash | `test_replay_uses_recorded_bundle` |
| T8 | A large what-if window exhausts the worker | Denial of service | `days` is at most 30, it runs as a job, and the result stores changed rows only | `test_whatif_window_capped` |
| T9 | The public discovery document leaks tenant data or policy detail | Information disclosure | `/.well-known/authzen-configuration` lists endpoints and capabilities only, the same for every caller (rule 9) | `test_authzen_discovery_public_no_tenant_data` |

## Abuse cases
- An admin narrows a policy, sees that the what-if denies the CFO's daily report, and publishes anyway. This is allowed, but the publish decision and the what-if result are both recorded.
- A producer adds a "must never" rule to hide a product from auditors. Rules can only deny agent and data actions. `audit.read` is not a valid `action_kinds` value.

## OWASP items in scope
- ASI02 (Tool misuse) and ASI03 (Privilege abuse): contract rules deny agent actions (A2). Covered by T1 and T6.
- ASI09 (Human-agent trust exploitation): what-if shows effects before publish (T2).
- LLM items: none. No model path changes.

## Residual risks
- The AuthZEN discovery document sits outside `/v1`, at `/.well-known/authzen-configuration`, under rule 9. It is public and holds no tenant data (T9).
- What-if covers only inputs recorded since 031.

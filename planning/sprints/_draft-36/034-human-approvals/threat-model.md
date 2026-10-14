# Sprint 034: Threat model

## Assets
- Approvals and their nonces. The canonical action hash.
- Restricted data behind approvals (HR salaries).
- The oversight log. Run control (stop, override).

## Trust boundaries crossed
- Requester to gateway (the action and its approval id).
- Approver in the console to the approvals routes (cookie and CSRF, or bearer).
- MCP client to the gateway (elicitation responses are untrusted input).
- Agent output to the approver view (the agent is untrusted).

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | An approval is replayed for a second call | Spoofing | Single-use consume in one `UPDATE ... WHERE used_at IS NULL` | `test_approval_single_use` |
| T2 | An approval is used for a changed action (other SQL, rows, snapshot, purpose) | Tampering | Hash over the canonical action; SQL normalised before hashing | `test_approval_hash_mismatch_each_field` |
| T3 | Two concurrent requests both consume one approval | Tampering | Row-level atomic consume | `test_approval_concurrent_consume_one_wins` |
| T4 | The requester approves their own request | Elevation | Separation of duties in the 023 model; the `duties` stage covers `approval.decide` and denies `separation_of_duties` | `test_requester_cannot_approve` |
| T5 | An approval overrides a later deny | Elevation | The approval stage only replaces "approval required"; later stages run | `test_approval_never_overrides_deny` |
| T6 | Approval forged by a tenant on another tenant's request | Elevation | RLS; foreign id answers 404 like a missing one | `test_approval_cross_tenant_404` |
| T7 | Agent text persuades the approver | Spoofing (ASI09) | Approver view built only from system fields | `test_approver_view_has_no_agent_text` |
| T8 | Approval or stop happens with no trace | Repudiation | Decision row plus oversight event in one transaction | `test_oversight_event_written_with_decision` |
| T9 | A stopped run keeps calling the gateway | Elevation | Stop revokes the run's tokens; next call 401 | `test_stop_revokes_run_tokens` |
| T10 | Evidence text leaks into events or records | Info disclosure | Events and records carry ids and hashes only | `test_approval_events_no_evidence_text` |
| T11 | Approval flood hides a real request | DoS | Pending requests per principal capped; extra ones deny with `approval_required` and no new row | `test_pending_approval_cap` |
| T12 | A forged elicitation answer approves an action | Spoofing | Elicitation never approves; only the console route does | `test_elicitation_cannot_approve` |
| T13 | A dashboard, report or alert floods approvers with requests on every render or run | DoS | No approval rows for `surface` `dashboard`, `report` or `alert`; the tile is `withheld` | `test_no_approval_rows_from_dashboards` |

## Abuse cases
- An agent splits one large query into many small ones to stay under the limit. Mitigation is out of this sprint (autonomy tiers, 039); recorded as a residual risk.
- An approver clicks through without reading (approval fatigue). The approval queue shows the policy reason and the data touched first. Rejecting is one click, as easy as approving.

## OWASP items in scope
- ASI09 Human-agent trust exploitation: T7.
- ASI02 Tool misuse: T2, T5.
- ASI03 Identity and privilege abuse: T4, T6.
- LLM06 Excessive agency: approvals gate high-impact actions.

## Residual risks
- The approval row stores the normalised SQL so the approver can read it. It is tenant-scoped and readable only with `approvals:decide`, and it is never in the decision record.
- Query splitting under the limit (see abuse cases).

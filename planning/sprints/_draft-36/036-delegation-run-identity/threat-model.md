# Sprint 036: Threat model

## Assets
- Delegation tokens and the delegation signing key.
- The user's authority that a run borrows.
- The delegation chain as evidence.

## Trust boundaries crossed
- Sandbox (untrusted agent) to the gateway's delegate route.
- Gateway to downstream services (MCP servers) with an audience-bound token.
- Platform to the identity provider (only if the Keycloak adapter is built).

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Agent asks for scopes the user lacks | Elevation | Subset check per hop | `test_delegation_widening_refused` |
| T2 | Agent acts for a user who never allowed it | Elevation | `may_act` check | `test_may_act_required` |
| T3 | Token for one downstream replayed at another (confused deputy) | Spoofing | Single `aud`, checked by the receiver | `test_audience_mismatch_refused` |
| T4 | Token outlives its run | Elevation | `exp` capped at run end; stop revokes | `test_token_after_run_end_refused`, `test_stop_revokes_delegation` |
| T5 | Forged token with another `act` chain | Spoofing | EdDSA signature, key from file, `alg` fixed | `test_forged_delegation_rejected` |
| T6 | Run A uses run B's identity | Spoofing | The delegate route takes the run from the run token, never the body | `test_delegate_uses_run_token_run` |
| T7 | Endless nesting to hide the origin | Tampering | Depth limit | `test_delegation_depth_limit` |
| T8 | Chain missing on a decision | Repudiation | Extension written for every run decision; test checks all rows | `test_every_run_decision_has_chain` |
| T9 | Token value leaks into logs or the table | Info disclosure | Only the `jti` hash stored; tokens hidden from `repr` and logs | `test_delegation_token_not_logged` |
| T10 | Cross-tenant read of delegation rows | Info disclosure | FORCE RLS | `test_delegation_tokens_rls` |
| T11 | A report job acts with the author's rights instead of the recipient's | Elevation | Report runs are delegations with `sub=recipient`, `act=job:insights.report.run`, and `may_act` must name `insights.report` | `test_report_run_delegation_chain` |
| T12 | A preview identity-provider feature reaches the main profile unreviewed | Tampering | `token-exchange-delegation` set only in the throwaway spike profile; ADR-0025 decides | `test_identity_profile_has_no_preview_features` |

## Abuse cases
- A prompt-injected agent requests a token for an MCP server the user can reach but this task does not need. The audience allow-list and the policy decide; the request is recorded either way.

## OWASP items in scope
- ASI03 Identity and privilege abuse: T1 to T7.
- ASI02 Tool misuse: audience limits stop a token being used on the wrong tool server.
- LLM06 Excessive agency: narrowing only.

## Residual risks
- Without SPIRE there is no workload attestation. A run id proves which run asked, not which binary ran.
- If the spike fails, tokens are platform-minted and downstream services must trust the platform key.

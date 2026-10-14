# Sprint 037: Threat model

## Assets
- The pinned card keys and approved card digests in the registry.
- The platform's card signing key.
- The tools and data an A2A caller can reach through `enforce()`.

## Trust boundaries crossed
- External agent to `/v1/a2a` (untrusted messages and cards).
- Registry admin to the approve route.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A peer claims to be a registered agent | Spoofing | Platform credential plus registry entry; card verified with a pinned key | `test_unregistered_agent_refused` |
| T2 | Card altered after approval (rug pull) | Tampering | Digest must equal `approved_digest` | `test_changed_card_blocked` |
| T3 | Card signed with the attacker's key | Spoofing | Only pinned keys verify | `test_unpinned_key_refused` |
| T4 | `alg` confusion or `none` in the JWS | Spoofing | Algorithm allow-list | `test_card_alg_none_refused` |
| T5 | A2A message used to inject instructions into a platform agent | Tampering (ASI01) | The message is untrusted content: it taints the run (Sprint 027 rules) | `test_a2a_message_taints_run` |
| T6 | A2A call skips policy | Elevation | `a2a.call` through `enforce()`; the `peer` stage after `boundary` and before `policy` | `test_a2a_goes_through_enforce` |
| T7 | Calls from a peer leave no trace | Repudiation | Decision row with the card digest | `test_card_digest_on_decision` |
| T8 | Platform card key stolen through config | Info disclosure | File-mounted, separate key, never logged | `test_card_key_not_logged` |
| T9 | Message flood | DoS | Rate stage applies per principal | `test_a2a_rate_limited` |
| T10 | Cross-tenant task read with `tasks/get` | Info disclosure | FORCE RLS; foreign task id answers like a missing one | `test_a2a_task_cross_tenant` |

## Abuse cases
- A trusted partner's card is swapped by a compromised publisher. The new digest blocks calls until a human re-approves.

## OWASP items in scope
- ASI07 Insecure inter-agent communication: T1 to T4, T7.
- ASI04 Supply chain: T2.
- ASI01 Goal hijack and LLM01 Prompt injection: T5.

## Residual risks
- A peer with a valid, approved card can still send hostile content. Taint and policy limit what it can make the agent do.
- The card at `/.well-known/agent-card.json` is public by rule 9 (recorded in Sprint 032). It holds the platform's public card only, no tenant data.

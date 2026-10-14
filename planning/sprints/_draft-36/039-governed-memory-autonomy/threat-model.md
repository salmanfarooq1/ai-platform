# Sprint 039: Threat model

## Assets
- Memory items and their trust tiers. The autonomy tier of each agent.
- The incident log as regulatory evidence.

## Trust boundaries crossed
- Agent (untrusted) to the memory write path.
- Untrusted content (documents, tools, A2A) into memory.
- Worker job to the autonomy state.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Injected instructions stored as memory and recalled later | Tampering (ASI06) | Guard stages on write; quarantine; low tier for untrusted sources | `test_poisoned_write_quarantined` |
| T2 | Agent raises an item's trust tier | Elevation | Tier set by the gateway from source; policy may only lower; no update grant on `trust_tier` | `test_agent_cannot_raise_tier` |
| T3 | Low-trust item used for a sensitive purpose | Elevation | Recall filter by purpose | `test_sensitive_purpose_excludes_low_tier` |
| T4 | Cross-tenant or cross-agent recall | Info disclosure | FORCE RLS plus `agent_id` filter | `test_memory_rls_and_agent_scope` |
| T5 | Memory read leaves no trace | Repudiation | `memory.read` decision with item ids | `test_recall_recorded` |
| T6 | Rogue agent keeps acting after repeated hits | Elevation (ASI10) | Automatic tightening by the job | `test_tier_lowered_on_guard_hits` |
| T7 | The agent or the job loosens its own tier | Elevation | Only an admin principal raises; run tokens and the job cannot | `test_only_human_admin_raises_tier` |
| T8 | Tier change forged or edited | Tampering | Change is a chained decision with a receipt; history append only | `test_autonomy_change_in_chain` |
| T9 | Incident record edited after reporting | Tampering | Transitions append only; `PATCH` only moves status forward | `test_incident_transitions_forward_only` |
| T10 | Memory content leaks into records or events | Info disclosure | Records hold hashes and ids only | `test_memory_records_no_content` |
| T11 | Memory flood fills storage | DoS | Writes count against rate limits; expiry required | `test_memory_write_needs_expiry` |

## Abuse cases
- A user plants a fact in memory through a chat turn, aiming at another user's later run. Memory is scoped per agent and tenant, tiered by source, and recalled only for matching purposes.

## OWASP items in scope
- ASI06 Memory and context poisoning: T1 to T5.
- ASI10 Rogue agents: T6 to T8.
- LLM04 Data and model poisoning: T1.

## Residual risks
- A poisoned item the guard misses gets a low tier, not a block. It can still be recalled for non-sensitive purposes.
- The autonomy job runs on a schedule, so tightening lags the triggering hits by up to one run of the job.

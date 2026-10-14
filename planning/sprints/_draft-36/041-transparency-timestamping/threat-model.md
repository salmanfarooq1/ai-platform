# Sprint 041: Threat model
## Assets
- The log checkpoint key and the TSA key (separate from the receipt key since Sprint 040).
- The log tables and the timestamps. Old receipts depend on them.
- The trust a reader places in a checkpoint seen earlier.

## Trust boundaries crossed
- API and worker to the TSA container (compose network, HTTP).
- Worker to an external anchor (only when one is set; off by default).
- An auditor's offline verifier reading files the platform produced.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A database owner rewrites leaves to hide a decision | Tampering | Consistency proof against a checkpoint the auditor kept; trigger refuses UPDATE and DELETE | `test_translog_consistency_detects_rewrite`, `test_translog_append_only_trigger` |
| T2 | A forged checkpoint signed with the receipt key | Spoofing | Checkpoints verify only with the checkpoint `kid`; the verifier rejects any other key | `test_checkpoint_rejects_receipt_key` |
| T3 | Back-dated timestamp after a clock jump | Tampering | Clock pre-flight against database and TSA time; refuse over `CLOCK_MAX_DRIFT_MS` | `test_stamp_refused_on_clock_drift` |
| T4 | A forged TSA token | Spoofing | Token checked against the pinned TSA certificate chain and the message imprint | `test_tsa_token_wrong_chain_fails`, `test_tsa_token_wrong_digest_fails` |
| T5 | Proof route reveals another tenant's leaves | Information disclosure | Per-tenant log under RLS; same 404 for foreign and missing | `test_inclusion_proof_cross_tenant_404` |
| T6 | TSA down blocks governed calls | Denial of service | Stamping is a job; decisions never wait on it; status shows `tsa: unavailable` | `test_decisions_continue_when_tsa_down` |
| T7 | Split view: two auditors see different checkpoints | Repudiation | External anchor adapters; the warning names the gap when off | `test_status_warns_without_anchor` |
| T8 | Data leaves the host by default | Information disclosure | `EXTERNAL_ANCHOR=none` default; egress guard in tests | `test_no_anchor_call_by_default` |

## Abuse cases
- An operator deletes yesterday's leaves to remove a bad decision. The trigger blocks it. A raw table rewrite still breaks consistency with saved checkpoints.
- A laptop wakes from sleep with a clock hours behind. Stamping stops until the clock is right.

## OWASP items in scope
- ASI10 Rogue agents: actions of an agent cannot be dropped from the record unseen once checkpointed.
- ASI04 Agentic supply chain: the TSA image is pinned by digest and checked by the licence gate.
- LLM Top 10 2026: none. No model input or output is touched here.

## Residual risks
- The TSA runs on the same host as the platform. A host owner can stamp anything. Only an external anchor removes this. Documented in ADR-0030.
- With no external anchor, a full rewrite of log and keys by a host owner is detectable only by someone who kept an older checkpoint.
- Losing the checkpoint or TSA key stops new proofs for old entries. The backup runbook covers it.

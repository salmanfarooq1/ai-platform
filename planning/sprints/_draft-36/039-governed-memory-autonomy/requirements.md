# Sprint 039: Governed memory and autonomy tiers. Requirements

A vertical slice in M3 Agent Runtime and M1 Gateway: agent memory as governed data, autonomy tiers that tighten on their own, and an incident log.

## Scope
1. **Memory as governed data.** Each item has `tenant_id` (RLS), a content hash, a source, provenance (run and decision id), a trust tier, a purpose and an expiry.
2. **Memory writes are actions.**
   - Every write goes through `enforce()` with policy.
   - Items from untrusted sources (documents, tool results, A2A messages, tainted runs) get a low trust tier.
   - A write the guard stages flag is quarantined, not recalled.
3. **Recall.**
   - Filters by trust tier and purpose. Sensitive purposes see only high-trust items.
   - Every memory read is recorded.
4. **Autonomy tiers per agent.**
   - Tighten automatically (more approvals, fewer tools) on guardrail hits, cost anomalies or eval regressions.
   - The trigger thresholds are placeholders: settings with defaults and a question in `planning/QUESTIONS.md`, never agreed rules.
   - Each change is a signed policy-change event.
   - Loosening is a human action, recorded.
5. **Incident log.** A serious-incident workflow in the EU AI Act Art. 73 shape. ADR-0028.
   - The Art. 73 report deadlines are settings with placeholder defaults and a logged question. Sprint 043 checks them against the adopted text.

## Out of scope
- Vector search over memory beyond the existing retrieval path.
- Reporting to an authority. The log prepares the record; sending it is a human step.
- The Art. 73 deadlines as fixed numbers in code. They are settings, and Sprint 043 checks them against the adopted text.

## Nav placement
Governance > Agent memory (items, tiers, quarantine, agent autonomy tiers). Evidence > Incidents.

## Questions this sprint closes
- None.

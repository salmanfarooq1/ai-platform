# Sprint 028: Agent registry, monitoring and memory. Requirements

Agents pillar (M3), with the Gateway (M1). One registry holds our agents, the client's agents and external agents. Agent templates and bring-your-own registration live there too. Agents are watched while they run and stopped when they go wrong. Their memory is governed data. This is a two-part sprint: part a covers items 1–4, part b covers items 5–7.

Source: old 037, old 039, the tracing part of old 044, plus new scope (gateway-proxy-and-agents and data-pillar-retrieval-memory research notes).

## Scope
1. **One registry for every agent kind** (extends the 016 registry).
   - Kinds: ours, client and external. Each has an owner, an agent id form (client metadata URL, SPIFFE id or card digest), allowed tools, an autonomy tier and the stopped flag.
   - Agent templates: a manifest (tools, purpose, policy defaults, model profile) that creates instances. The data agent and the integration agent (027) are the first templates.
   - Bring-your-own registration: a client agent registers through an API or by its Agent Card. It gets the request contract and an egress template (016) as its checklist.
   - A changed card or manifest needs re-approval before calls are allowed again.
2. **A2A v1.0** (`a2a-sdk==1.1.5`, pin re-checked against the primary spec).
   - Inbound A2A calls go through the gateway (the 016 proxy route and the `peer` stage).
   - The caller must be registered and approved.
   - Cards are signed (JWS) and verified against the key pinned in the registry. The card digest goes on every decision.
   - The platform publishes its own signed card at `/.well-known/agent-card.json` (rule 9).
3. **Tracing.**
   - The OTel collector (`otel/opentelemetry-collector-contrib:0.161.0`, profile `observability`).
   - OTel GenAI agent spans (`invoke_agent`, `chat`, `execute_tool`) behind the opt-in flag, with the conventions version pinned.
   - Every gateway span carries `decision_id`, and job spans continue the request trace.
   - Redaction: no prompt, answer, document or SQL text by default, in the app and again in the collector.
4. **Runtime monitoring and breakers.**
   - Loop detection and budget breakers per run trip automatically and stop the run. Thresholds are placeholders.
   - Anomaly alerts: denial spikes, cost spikes, new tools, and an agent calling outside its usual pattern.
   - Stop-run from the console and API (019 route), plus the registry stop flag.
   - Breakers run in the gateway and worker, never inside the agent.
5. **Memory as governed data.**
   - Each item has `tenant_id` (RLS), a content hash, a source, provenance (run and decision id), a trust tier, a purpose and an expiry.
   - Writes are `memory.write` actions through policy. Untrusted sources get a low trust tier. Flagged writes are quarantined.
   - Recall filters by trust tier and purpose, and every read is recorded.
   - Token budget per run, with summarise-on-overflow. The summary keeps provenance links.
6. **Autonomy tiers and incidents.**
   - Tiers tighten automatically on guardrail hits, cost anomalies or eval regressions. Each change is a signed policy-change event. Loosening is a recorded human action.
   - Incident log in the EU AI Act Art. 73 shape. The deadlines are settings with placeholder defaults; 030 checks them.
7. **ADRs.** ADR-0026 (A2A, cards, registry) and ADR-0028 (memory and autonomy).

## Out of scope
- Outbound A2A calls from our agents to outside agents.
- A trace store and trace UI (Tempo, Jaeger). Traces go to the collector's file exporter.
- Third-party memory frameworks (Mem0, Letta, Zep) as the store. Memory stays a governed Postgres table.
- Changed from old 037 and 039: one registry for all agent kinds with templates, and runtime monitoring with breakers is new here, not at the end of the program.

## Nav placement
- Governance > Agents: registry, templates, stop, autonomy tier.
- Governance > Agent runs: live breakers and alerts.
- Governance > Memory.
- Platform > Observability.

## Questions this sprint closes
- Proposes the default for owner question Q-10 (kill-switch authority): tenant admin and platform operator, both recorded.

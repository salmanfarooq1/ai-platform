# Content style

How the product talks. These rules apply to every word a person reads in the UI, on the public pages and in the docs.

## Voice and tone
- Short, plain sentences. One idea each.
- Say what is true now. Do not promise what is planned.
- Name the thing: "Add documents", not "Submit".
- Say what happened, then what to do next. Do not blame the person.
- Technical detail belongs in the console, not on the workspace or the public pages.
- No filler and no hype. If a sentence works without an adjective, drop the adjective.
- Never invent a number, a customer or a quote.

## Audience order
1. **The person accountable for the agents.** A team lead, an owner or a risk owner. They want to control what agents can do and to see what they did. The landing page speaks to them first.
2. **Engineers who run the agents.** They want the mechanism. It goes on How it works, in the console and in the docs.

Lead with the first reader's question: "Can I limit what my agents do, and can I see what they did?" Put the mechanism one click away.

## Glossary
Use these words with these meanings, everywhere.

| Term | Meaning |
|---|---|
| Decision | One check by the gateway and its result, allow or deny. Stored as a row with an id, action, resource, stage, reason, policy version and a hash of the input. |
| Receipt | The readable view of one decision: ids, policy version, tenant, principal, action, resource, stage, reason and the input hash. |
| Signed receipt | A decision with its place in the tenant's hash chain and an Ed25519 signature. Anyone with the public key can check it offline. The Trust page and `GET /v1/receipts/{id}` give it. |
| Request | One call to the platform. It can cause several decisions, for example a search checks a knowledge base read and a model call. A request id groups them. |
| Run | One agent request handled by the agent runtime. It has an execution id, and every decision the run causes carries it. Its status is Running, Finished, Failed or Stopped. The runtime keeps status in memory, so an older run says "Not tracked". |
| Sandbox | The isolated space a run can execute in (`AGENT_RUNTIME=openshell`). Its only network route is the gateway, it can write one work directory, and it has CPU, memory and time limits. |
| Sandbox event | Something the sandbox reported about a run: it started or exited, it blocked a network call or a file access, or it hit a limit. Shown on the run's steps next to the gateway decisions. It is not a decision and has no policy version. |
| Execution id | The id of one run. It groups all the decisions of that run. It is shown in mono and can be copied. |
| Policy | A tenant's document that narrows what its callers may do: knowledge bases, tools, models, tool calls and tokens. |
| Policy version | The number of the policy that applied. Each change adds a version. "default" means the tenant had no policy and the platform defaults applied. |
| Tenant | One organization's isolated space. The database keeps tenants apart. |
| Principal | Who or what makes a call: a person or an agent identity. API keys belong to a principal. |
| Scope | A permission on a key, such as `kb:read`, `query`, `agent` or `audit:read`. |
| Knowledge base | A named collection of documents that can be searched. It is identified by a slug. |
| Verdict | The outcome of a check: allowed or denied. "Needs approval" is designed but not built. |
| Stage | One step of the gateway's checks: identity, scope, policy, input guardrails, rate limit, token budget. Two more name faults: the gateway itself and the decision record. |

## Reason sentences
Every reason code has one sentence. The catalogue is `gateway/reasons.py`, served at `/v1/reason-codes`. The UI never writes its own reason text.

- One sentence, 25 words or fewer.
- Start with the thing that was checked: "The policy does not list this knowledge base."
- Say what happened, not who is at fault.
- Where the person can act, say how: "Try again shortly."
- Keep the code out of the sentence. The code is shown next to it, in mono.
- A stop with a policy key behind it shows that key as the policy field, for example `allowed_kbs`. A stop with no policy key says so.
- The stage on the decision row is the source of truth. The catalogue's stage is only a hint.
- `query_blocked` is also raised by the built-in injection patterns, which every tenant has. Name `blocked_terms` as the policy field only when the tenant policy really holds blocked terms.
- A code the catalogue does not know still gets a plain fallback sentence, so a deny is never shown without words.

## What content may claim
Built and tested. Every claim on a public page maps to one of these items. `ui/src/landing/claims.ts` holds the map, and `npm run copy-check` prints it.
1. One gateway for every model, tool and knowledge-base call. Agent code does not import the model client, and a test checks this.
2. Tenant policies that can only narrow access (knowledge bases, tools, models, tool-call and token limits). They are versioned, and every request is checked against the active version.
3. A decision record for every call, allow or deny, with a reason, the policy version and an input hash. The input text is not stored. (A record can also be signed as a receipt: item 9.)
4. Tenant isolation enforced by the database.
5. Fail closed: if a check or the decision record cannot be written, the call is denied.
6. Rate limits, daily token budgets and a daily cost cap per tenant.
7. Read-only preview sessions. The API key stays on the server in a secure cookie session.
8. Works over MCP for agent clients.
9. Signed receipts: a decision can be signed (Ed25519) together with its place in a per-tenant hash chain, and the receipt can be checked offline with a public key. Say "tamper evident", never "tamper proof".
10. Retention: decision records are kept for a set period (90 days by default, a tenant may set its own), and a purge leaves a checkpoint so the remaining records still verify.
11. A daily cost cap per tenant that stops calls when it is reached, and stops them if the check cannot run.
12. An eval gate in CI: a fixed suite with a stored baseline that fails the build when a score drops. It runs with a fake model, so it guards the code and not a provider.
13. Metrics in Prometheus format, and an optional Grafana dashboard.

The How it works page also rests on ADR-0006 (the order of the checks, and that the first deny wins).

## What content must not claim yet
Planned or not built. Do not write these as if they exist.

| Planned | Sprint |
|---|---|
| Background jobs and live ingestion progress | 007 |
| Anchoring the chain outside the database, signing keys in a managed key service, eval scores from real providers in CI | not scheduled |
| Sandboxed agent execution (NVIDIA OpenShell): built behind a port and run live on one host (Docker driver, OpenShell 0.1.2), not on the standard images or any other driver | 009 |
| Kafka event streaming | 010 |
| Approvals (escalate), PII redaction, OPA policies | not scheduled |
| Hosted availability, uptime or scale numbers | hosting is parked |
| Customers, logos, testimonials | none exist |

## Banned words and characters
- **Characters:** the long dash (U+2014) and the en dash (U+2013). Use a hyphen, a period or a colon.
- **Words:** "elevate", "seamless", "unleash", "next-gen", and the word that means a canned trial run of the product. The hosted mode is called `public-preview`.
- **Also out:** invented numbers, version labels in the hero, a brand name for the platform, and a status dot that is not a real state.
- `npm run copy-check` in `ui/` scans the UI source for these and checks the headline and subline.

## Fixed copy
- **Headline:** Your agents can only ever do less.
- **Subline:** Control what your agents can do. See everything they did.
- **Walkthrough:** the guided first run is called the walkthrough.

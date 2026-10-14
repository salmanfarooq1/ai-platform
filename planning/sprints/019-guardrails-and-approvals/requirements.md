# Sprint 019: Guardrails and approvals. Requirements

Gateway pillar (M1 and M2). Adds PII and guard-model stages on input and output, a port for third-party guardrails, and the one approval model every later sprint reuses. The model covers runtime approvals bound to the exact action, stop and override, and an oversight log.

Source: old 038, old 034, plus the approval-model parts of old 023 and new scope (enterprise-gaps-how, gateway-proxy-and-agents research notes).

## Scope
1. **Presidio stage** (`presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364`).
   - Runs on input and output, for embedded calls and for the 016 proxy routes (MCP and the OpenAI-style route).
   - The spaCy model is pre-fetched into the image. Nothing is downloaded at runtime.
   - Masking by entity type, set in policy (018).
2. **Local guard model** `granite3-guardian:2b` from `models.lock`, as a stage. Its digest and verdict go into the decision record (record v2 extension `guard`).
3. **Guard-provider port** (`GuardProvider`).
   - Adapters: the local guard model, Presidio, and a fake for tests. A third-party engine the client already owns (Prisma AIRS, Lakera, F5 and similar) can be added as an HTTP adapter.
   - Its verdict, provider id and version go into our receipt. A provider timeout or error is a deny (`guard_unavailable`), never a skip.
4. **Measurement.**
   - A labelled set for precision and recall, with the dataset hash recorded.
   - A latency budget per stage, which must fit inside the 016 callout budget for proxy routes.
   - Thresholds and budgets are placeholders: settings with defaults and a question in `planning/QUESTIONS.md`.
5. **One approval model** (defined here, reused by 024 access requests).
   - An approver group is copied onto the request. Chains go by sensitivity. Separation of duties: the requester never approves.
   - Runtime approvals are bound to a canonical action hash over the SQL or tool arguments, parameters, snapshot id (when present), principal, purpose and policy bundle hash. Any change gives a different hash.
   - Approvals are single use (nonce), short-lived, and re-checked at execution. Every other stage runs again, so an approval never overrides a deny.
   - Route `/v1/approvals` with a `kind` field: `runtime_action` now, `access_request` from 024. New scope `approvals:decide`.
   - `approval_required` from 018 becomes real. On `surface` `dashboard`, `report` or `alert` (029) it becomes a withheld tile, not an approval.
6. **Channels.**
   - **Kernel inbox:** `core/inbox.py` and `/v1/inbox`, built here (moved from the BI sprint). Each pending approval posts `approval_pending` to each approver.
   - **Console queue:** Governance > Approvals.
   - **MCP elicitation** on the 016 front, with URL mode for anything sensitive.
   - **AuthZEN approval profile** shape on the 018 API, labelled "draft-compatible".
   - **Approval webhook:** a signed outbound event that a Jira or ServiceNow automation can turn into a ticket. Jira Automation cannot verify HMAC, so the docs describe a small relay. The decision always comes back through `/v1/approvals`, never through the ticket.
7. **Stop and override (Q22).**
   - `POST /v1/agent/runs/{execution_id}/stop` and `.../override`.
   - The stop also sets the 016 registry flag when an admin asks for it.
   - Human oversight log: who oversaw, stops, overrides, approvals and rejections.
8. **Approver view.** The approver sees system evidence: the action, the data touched and the policy reason. Never the agent's own explanation (ASI09). Journey: a tool call to a payments tool on the reference company needs an approval. ADR-0024, ADR-0027.
9. **Q37 re-check.** Does the pinned OpenShell log an event when it refuses a file read? Record the answer.

## Out of scope
- The trifecta breaker and session taint. They start in 027, where agents first read client data, and read their rules from 018 policy data.
- Resuming a paused run after approval. The caller sends the same action again with the approval id.
- SSO approvers (020). Until then approvers are existing principals with `approvals:decide`.
- Over-limit data queries asking for approval (025 and 027 use this model).
- Changed from old 034: the inbox and the approval model are built here, because insights and access requests now come later.

## Nav placement
- Governance > Guardrails: stages per tenant, masking by entity type, providers, and the last measured precision, recall and latency.
- Governance > Approvals: a queue and an Oversight log tab.
- Stop and Override buttons on Governance > Agent runs.

## Questions this sprint closes
- Q22: yes, a stop route, with scope `agent` for the run's own principal or `admin`.
- Q37: closed with the re-check result, or carried with the evidence.

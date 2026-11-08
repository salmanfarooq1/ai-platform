# Sprint 019: Guardrails and approvals. Requirements

Gateway pillar (M1 and M2). Adds PII and guard-model stages on input and output, a port for third-party guardrails, and the one approval model every later sprint reuses. The model covers runtime approvals bound to the exact action, stop and override, and an oversight log.

Source: old 038, old 034, plus the approval-model parts of old 023 and new scope (enterprise-gaps-how, gateway-proxy-and-agents research notes).

Depends on: 016.

## Scope
1. **Ordered guardrail chain and port.**
   - Define a `Guardrail` port and an ordered chain bound per action and direction in tenant policy. Run guardrails on both input and output for embedded calls and the 016 proxy routes.
   - Presidio (`presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364`) runs before and after the model call. The spaCy model is pre-fetched into the image. Nothing is downloaded at runtime.
   - Masking by entity type is set in policy (018).
2. **Secrets and regional identifiers.** Secrets recognition uses gitleaks-style rules stored as data. Regional identifiers are data, not code branches.
3. **Local guard model.** Re-select the model from Granite Guardian 3.3 or 4.1 (Apache-2.0). Confirm the official Ollama library tag and supply-chain rule at sprint start. Store its digest and verdict in the decision record (record v2 extension `guard`).
4. **Provider adapters and measurement.**
   - Adapters include the local guard model, Presidio and a fake for tests. A third-party engine can be added as an HTTP adapter. Its verdict, provider id and version go into the receipt. A provider timeout or error denies (`guard_unavailable`); it never skips.
   - Keep a labelled precision and recall set with its dataset hash. Set a latency budget per stage that fits inside the 016 callout budget. Thresholds and budgets remain settings with defaults and an open question.
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
7. **Stop and override (Q22).**
   - `POST /v1/agent/runs/{execution_id}/stop` and `.../override`.
   - The stop also sets the 016 registry flag when an admin asks for it.
   - Human oversight log: who oversaw, stops, overrides, approvals and rejections.
8. **Approver view.** The approver sees system evidence: the action, the data touched and the policy reason. Never the agent's own explanation (ASI09). Journey: a tool call to a payments tool on the reference company needs an approval. ADR-0024, ADR-0027.
9. **AI-generated content disclosure.** Meet EU AI Act Article 50 disclosure requirements.
10. **Streaming modes.** `buffer_all` is the default. `windowed_scan` is opt-in and documented as best effort because sent chunks cannot be taken back.
11. **Q37 re-check.** Does the pinned OpenShell log an event when it refuses a file read? Record the answer.

## Out of scope
- The trifecta breaker and session taint. They start in 027, where agents first read client data, and read their rules from 018 policy data.
- Approval webhook and AuthZEN approval profile (030).
- Resuming a paused run after approval. The caller sends the same action again with the approval id.
- SSO approvers (020). Until then approvers are existing principals with `approvals:decide`.
- Over-limit data queries asking for approval (025 and 027 use this model).
- Changed from old 034: the inbox and the approval model are built here, because insights and access requests now come later.

## Nav placement
- Governance > Guardrails: stages per tenant, masking by entity type, providers, and the last measured precision, recall and latency.
- Governance > Guardrails: a console library, ordered bindings and activity counts from decision records. Every change is a recorded decision.
- Governance > Approvals: a queue and an Oversight log tab.
- Stop and Override buttons on Governance > Agent runs.

## Questions this sprint closes
- Q22: yes, a stop route, with scope `agent` for the run's own principal or `admin`.
- Q37: closed with the re-check result, or carried with the evidence.

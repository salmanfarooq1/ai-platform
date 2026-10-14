# Sprint 034: Human approvals. Requirements

A vertical slice in M1 Gateway and M2 Evidence: runtime approvals bound to the exact action, a stop and override route, and a human oversight log.

## Scope
1. **"Approval required" becomes real.** Until now (Sprint 031) it is recorded and treated as a deny.
   - An approval is bound to a canonical action hash over: the SQL or tool arguments, the parameters, the snapshot id, the principal, the purpose and the policy bundle hash.
   - Any change to one of these gives a different hash, and the approval does not match.
2. **Approval rules.** Reuse the approval model from Sprint 023 (approver group copied onto the request, chains by sensitivity, separation of duties).
   - Single use (a nonce) and a short expiry.
   - Re-checked at execution: every other stage runs again, so an approval never overrides a deny.
   - The requester never approves, including a steward on their own product.
   - Runtime approvals share the `/v1/approvals` route and model with Sprint 023 access requests. A `kind` field tells them apart: 023 uses `access_request`, this sprint adds `runtime_action`.
   - New scope `approvals:decide` (introduced here) decides runtime approvals. Access requests keep `data:steward` (from Sprint 021, used by Sprint 023).
3. **Channels.**
   - An approval queue in the console (Governance > Approvals).
   - Each new pending approval posts an `approval_pending` item to the kernel inbox (`/v1/inbox`, Sprint 029) of each approver.
   - MCP elicitation for MCP clients. URL mode for anything sensitive.
   - The AuthZEN access request and approval profile shape on the AuthZEN API (Sprint 032), labelled "draft-compatible".
4. **Stop and override (Q22).**
   - `POST /v1/agent/runs/{execution_id}/stop` ends a run.
   - `POST /v1/agent/runs/{execution_id}/override` marks a run's output as overridden by a human, so it is withheld.
   - A human oversight log: who oversaw, stops, overrides, approvals and rejections.
5. **Approver view and journeys.**
   - The approver sees system evidence (the query or tool arguments, the data touched, the policy reason), never the agent's own explanation (ASI09).
   - Over-limit queries from Sprint 026 now ask for approval instead of a deny.
   - Dashboards, reports and alerts never create approvals. `approval_required` on `surface` `dashboard`, `report` or `alert` shows the tile as `withheld`.
   - The salary journey on the reference company needs an approval. ADR-0024.

## Out of scope
- Resuming a paused agent run after approval. The caller sends the same action again with the approval id.
- SSO approvers. Until Sprint 035, approvers are existing principals with `approvals:decide` (runtime actions) or `data:steward` (access requests).
- Autonomy tiers and incidents (Sprint 039). COSE receipts (Sprint 040).

## Nav placement
Governance > Approvals (a "Runtime actions" tab next to access requests, and an "Oversight log" tab). Stop and Override buttons on Governance > Agent runs.

## Questions this sprint closes
- Q22: yes, a stop route, with scope `agent` for the run's own principal or `admin`.

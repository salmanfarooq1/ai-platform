# Sprint 023: Access requests and grants. Requirements

Vertical slice, modules M4 Data Plane and M1 Gateway. Contract first, then backend, then UI, then e2e.

## Scope
1. **Listings.**
   - A certified product can be listed for other tenants or for teams (access groups) in its own tenant.
   - A listing requires a classification on the product and on every column.
2. **Access requests and one approval model.**
   - A request names the product, columns, an optional row filter, a purpose and a justification, and an expiry.
   - The approver chain is chosen by sensitivity from the tenant's approval policy, and copied onto the request when it is made.
   - Separation of duties: the requester never approves. The product owner and its certifying steward never approve requests on that product. One principal approves at most one step.
   - Approvers are existing principals with `data:steward` in the named group, until Sprint 035.
   - One approval model and one route, `/v1/approvals`, with a `kind` field. This sprint has the kind `access_request`. Sprint 034 reuses the model and the route for runtime actions.
3. **Grant queue.**
   - An approved request becomes a grant through a worker job. "Approved" and "granted" are separate states.
   - A grant carries purpose, columns, row filter and expiry. The worker re-checks the request before it grants.
4. **Revocation, expiry and extracts.**
   - A steward can revoke a grant. A grant past its expiry gives no access, with or without the expiry job.
   - Allowed extracts leave through signed, short-lived download URLs.
   - Extracts go through a new `DataAccess.extract` method on the 013 port.
5. **Pages:** Marketplace, My access, and an Approvals queue for access requests.

## Out of scope
- Enforcing row filters and masks inside ad hoc queries (024). Until then, a grant is used for extracts only, and masked columns are withheld from extracts.
- Live queries across tenants. Approvals for runtime actions (034). SSO groups (035).

## Nav placement
Workspace > Marketplace, Workspace > My access, Governance > Approvals (access requests).

## Questions this sprint closes
- None from `planning/QUESTIONS.md`.

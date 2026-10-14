# Sprint 024: Grants and query enforcement. Requirements

Data pillar (M4), with the Gateway (M1). People request access with a purpose. Approved requests become grants. Grants are enforced inside every query by rewriting the SQL, on every adapter. Engine or warehouse policies are added only as a second layer.

Source: old 023, old 024, plus new scope (integration-data-connectors research note).

## Scope
1. **Listings.**
   - A certified product (023) can be listed for teams (access groups) in its own tenant, or for other tenants in a multi-tenant deploy.
   - A listing needs a classification on the product and on every column.
2. **Access requests on the 019 approval model.**
   - A request names the product, columns, an optional row filter, a purpose, a justification and an expiry.
   - It uses `/v1/approvals` with `kind` `access_request`. The approver chain is chosen by sensitivity and copied onto the request.
   - Separation of duties: the requester, the product owner and its certifying steward never approve this request. One principal approves at most one step.
   - Approvers have `data:steward`. With 020 in place, they can be SSO groups.
3. **Grant queue, revocation and extracts.**
   - An approved request becomes a grant through a worker job that re-checks the request. "Approved" and "granted" are separate states.
   - A grant carries purpose, columns, row filter and expiry. A grant past its expiry gives no access, with or without the expiry job.
   - A steward can revoke a grant. Revoking cancels running queries that use it.
   - Extracts go through `DataAccess.extract` and leave through signed, short-lived URLs. Masked columns are withheld.
4. **Rewrite, not views, on every adapter.**
   - sqlglot parses the query in the adapter's dialect (DuckDB for Direct and Lakehouse, Trino for Federated). Each table is replaced with the grant's filtered and masked subquery.
   - Only rewritten references are allowed. Table functions and any unrewritten relation are denied.
   - Masks and filters come from the grant and the contract classification.
   - Checks: file pruning still works on DuckLake, and filters are still pushed down to a Direct Postgres source. The results go in evidence.
5. **Second layer** (defence in depth, never the only control).
   - The Federated adapter, built in full if the 021 spike passed. Trino's OPA plugin receives the same grant as row filters and masks from our policy bundle.
   - For a Native warehouse adapter, when one exists, the same grant can be pushed as a native row-access or masking policy. Not built here.
6. **Purpose binding and limits.**
   - The 018 purpose stage now checks the declared purpose against the grant's purpose. A mismatch is a deny.
   - Minimum group size: aggregates over classified columns need at least k rows per group. k comes from the contract, else from a placeholder setting with a question.
   - Over-limit queries ask for approval on the 019 model instead of a plain deny.
   - Cache keys include the principal, grant id and grant version.
7. **Proof.**
   - A bypass corpus of 50 or more cases as tests, run against Direct and Lakehouse (and Federated if built).
   - Journey: a salary question on the reference company's HR data needs an approval and returns masked rows.
   - ADR-0019.

## Out of scope
- The full parsed SQL guard (function allowlist, cost limits) and the semantic layer (025). This sprint denies table functions and any unrewritten relation, nothing more.
- Live queries across tenants. Cross-tenant grants stay extract-only.
- Changed from old 023 and 024: the approval model and purpose stage come from 019 and 018, the rewrite covers every adapter, and Trino or native policies are a second layer.

## Nav placement
- Workspace > Marketplace and Workspace > My access.
- Workspace > Data query: a governed SQL box for analysts with grants.
- Governance > Approvals: the access requests tab.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. The default k and the over-limit thresholds are placeholders with questions.

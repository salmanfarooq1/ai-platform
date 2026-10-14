# Sprint 024: Query enforcement. Requirements

Vertical slice, modules M4 Data Plane and M1 Gateway. Grants from Sprint 023 are enforced inside queries.

## Scope
1. **Rewrite, not views.**
   - Parse SQL with sqlglot (duckdb dialect). Replace each table with the grant's filtered and masked subquery.
   - Only rewritten references are allowed. Anything else is a deny.
   - Column masks and row filters come from the grant and the contract classification.
2. **Minimum group size.** Aggregates over classified columns need at least k rows per group. k comes from the contract, else from a setting. The default k is a placeholder with a question in `planning/QUESTIONS.md`, not an agreed rule.
3. **Purpose stage.** A Python stage in `enforce()`.
   - The declared purpose must match the grant's purpose. A mismatch is a deny.
   - OPA takes this over in Sprint 031 without changing behaviour.
4. **Cache and revocation.**
   - Cache keys include principal, grant id and grant version.
   - Revoking a grant cancels running queries that use it.
5. **Proof.**
   - A bypass corpus of 50 or more cases, run as tests.
   - A check that file pruning still works after rewriting.
   - ADR-0019.

## Out of scope
- The full parsed SQL guard (function allowlist, EXPLAIN cost limits) and the semantic layer (026). This sprint denies table functions and any unrewritten relation, nothing more.
- Queries across tenants. Cross-tenant grants stay extract-only (023).
- Approval for over-limit queries (034). Until 034, an over-limit query is a deny, not "approval required".

## Nav placement
Workspace > Data query: a governed SQL box for analysts with grants.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`.

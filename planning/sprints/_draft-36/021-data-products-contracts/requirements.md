# Sprint 021: Data products and contracts. Requirements

Vertical slice, module M4 Data Plane. Contract first, then backend, then UI, then e2e.

## Scope
1. **Products and contracts as documents.**
   - Data products are ODPS 1.1 documents. Contracts are ODCS 3.2 documents.
   - Both are stored as validated JSONB, with `tenant_id` and RLS.
   - `datacontract-cli` (re-check the pin; its `duckdb` extra must match `duckdb==1.5.5`) lints and tests contracts.
2. **Contract versions.**
   - Semantic versions. A native diff marks breaking changes: removed column, narrowed type, tighter rule, changed classification. Each is a major change.
   - A major version needs a new output port and a deprecation window on the old one.
3. **Product lifecycle.**
   - An explicit table of legal transitions: `draft`, `in_review`, `certified`, `degraded`, `deprecated`, `retired`.
   - Every transition writes an audit event. An illegal transition is refused.
   - New credential scope `data:steward` for steward steps. New action kind `product.certify` for those steps.
4. **Classification, glossary and aspects.**
   - Classification and sensitivity are required before review.
   - Glossary terms, linked to products and columns.
   - Aspect types are JSON Schema documents. Aspects are validated against them.
5. **Catalog search and Products page.**
   - Postgres full-text search over products, columns and glossary terms.
   - Products page. ADR-0018.

## Out of scope
- Certification checks and quality scores (022). The `in_review → certified` transition exists, and Sprint 022 adds the checks that gate it.
- Listings and access requests (023). Enforcing masks from classification (024).

## Nav placement
Data > Products.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`.

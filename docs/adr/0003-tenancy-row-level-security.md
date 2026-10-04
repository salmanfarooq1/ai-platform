# ADR 0003: Tenancy with tenant_id and row-level security

**Status:** Accepted

## Context
- Tenancy today is a free-text `namespace` column, and the caller chooses its own value (`api/middleware/rate_limit.py`, `config.py` `NAMESPACE_REGISTRY`).
- Any caller can read any namespace.

## Decision
- Add a `tenants` table. Every tenant-owned table gets a non-null `tenant_id`.
- Postgres **row-level security** policies filter on `current_setting('app.tenant_id')`. The app sets this per transaction from the authenticated principal.
- Namespaces become **knowledge bases** owned by a tenant.
- Existing rows are backfilled to one default tenant.

## Consequences
- Isolation holds even when application code has a bug.
- Every DB access must run inside a tenant-scoped transaction. The pool helper does this.
- Migrations and admin jobs need an explicit role that bypasses row-level security, and it is audited.

## Alternatives considered
- **Filtering only in app code:** one missed `WHERE` leaks data.
- **A schema or database per tenant:** too heavy for free tiers and many tenants.

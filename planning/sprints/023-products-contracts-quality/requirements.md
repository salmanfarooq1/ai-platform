# Sprint 023: Products, contracts and quality. Requirements

Vertical slice, Data pillar, module M4 Data Plane, with the `duties` stage in M1 Gateway. Contract first, then backend, then UI, then e2e.

Source: old 021, old 022, the "contract rules into policy" part of old 032, plus new scope (integration-data-connectors: catalog import).

## Scope
1. **Products and contracts as documents.**
   - Data products are ODPS 1.1 documents. Contracts are ODCS 3.2 documents. Both are validated JSONB with `tenant_id` and RLS.
   - `datacontract-cli` (re-check the pin; its `duckdb` extra must match the DuckDB pin) lints and tests contracts. It never opens its own connection or reads secrets.
   - A product's output can sit on any 021 adapter: Direct (read in place), Lakehouse or Federated. The contract's columns are checked against the dataset's schema through `DataAccess` and the `QueryEngine` port.
2. **Contract versions.**
   - Semantic versions. A native diff marks breaking changes: removed column, narrowed type, tighter rule, changed classification. Each is a major change.
   - A major version needs a new output port and a deprecation window (`CONTRACT_DEPRECATION_DAYS`, a placeholder setting) on the old one.
3. **Lifecycle.**
   - A table of legal transitions: `draft`, `in_review`, `certified`, `degraded`, `deprecated`, `retired`. An illegal transition is refused.
   - Every transition writes a `product_events` row and the event `platform.products.lifecycle.changed.v1`. Test: `test_event_per_transition`.
   - Scope `data:steward` (from this sprint) and action `product.certify` cover the steward steps. Edits and owner steps are `data.write`.
4. **Classification, glossary, aspects, search.**
   - Classification and sensitivity are required before review (`classification_required`).
   - Glossary terms link to products and columns. Aspect types are JSON Schema documents.
   - Catalog search is Postgres full text (`websearch_to_tsquery('simple', ...)`) over products, columns and terms.
5. **Catalog import (new).**
   - Import a client's catalog from OpenMetadata or DataHub through their API: tables, columns, owners, tags and glossary terms become draft products, columns and term links. We run neither server.
   - The importer sits behind a port of our own, with a fake for tests and a contract suite. Credentials come from the 021 secret store. Calls go out only to hosts on the egress allowlist.
   - Imported items keep their source and external id. They are never certified by import: a steward reviews each one. A re-import shows drift (added, removed, changed) and changes nothing by itself.
   - Lineage import is Sprint 025.
6. **"Must never" rules into policy (moved from old 032).**
   - ODCS 3.2 agent-context rules ("must never" rules and usage instructions) are compiled into policy data per product, read by the Python engine and by OPA (018).
   - The decision-table suite from 018 gets rows for both engines. Rego changes only through the repo and CI.
7. **Auto-checks and certification.**
   - A registry of named checks, each with a dimension and a blocking flag: missing owner, missing classification, PII columns not classified, no lineage, stale data, broken SLO.
   - `no_lineage` returns `stub` until 025 wires `LineageLookup`. `pii_not_classified` starts with regex detectors and column-name hints. The 019 Presidio recognisers may back it (changed: old 022 left this to a later guardrail sprint).
   - Certification is a decision through `enforce()`. The `duties` stage denies `separation_of_duties` (the requester or owner certifies) and `certification_blocked` (a blocking check failed on the current snapshot). `Action.context` carries server-built facts only.
   - The `data` record extension gains `quality_evaluation_id`.
8. **Contract checks, quality score and re-evaluation.**
   - Contract quality rules run through `QueryEngine`, or as dbt tests for dbt-built products. Rules of type `sql` are refused (`rule_type_not_supported`) until the 025 guard exists.
   - Auto-profiling (DuckDB `SUMMARIZE`, `ydata-profiling` on a sample) drafts rules. A steward approves or rejects each draft.
   - Score: weighted pass rates for completeness, validity, freshness and uniqueness, with blocking versus warning checks and hysteresis. Freshness SLOs come from the contract. Results are stored per snapshot id, as counts and rates only.
   - A scheduled job moves products between `certified` and `degraded`. `QUALITY_*` weights and thresholds are placeholder settings.

## Out of scope
- Running OpenMetadata or DataHub (rejected in `stack.md`). Importing their lineage (025).
- Listings, access requests and masks from classification (024).
- Contract rules of type `sql` (025). Notifications.

## Nav placement
Data > Products (including Import). Data > Quality.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Placeholder weights, thresholds and limits are added there for the owner.

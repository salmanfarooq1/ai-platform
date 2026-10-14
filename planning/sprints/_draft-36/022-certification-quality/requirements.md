# Sprint 022: Certification and quality. Requirements

Vertical slice, module M4 Data Plane, with one gateway stage (M1). Builds on the Sprint 021 lifecycle.

## Scope
1. **Auto-check registry.** Named functions, each with a dimension and a blocking flag:
   - missing owner, missing classification, PII columns not classified, no lineage (a stub until 025 adds the `LineageLookup` port), stale data, broken SLO.
2. **Steward certification.**
   - Blocking checks must pass on the current snapshot.
   - Certification is a decision through `enforce()`, recorded like any other.
   - The requester (who moved the product to review) and the certifying steward are different principals.
3. **Contract checks and auto-profiling.**
   - Contract quality rules run on DuckDB through the `QueryEngine` port. Where the product is dbt-built, they run as dbt tests.
   - Auto-profiling drafts rules from DuckDB `SUMMARIZE` and `ydata-profiling` on a sample.
   - A steward approves or rejects each draft.
4. **Quality score.**
   - Weighted pass rates by dimension: completeness, validity, freshness, uniqueness.
   - Blocking versus warning checks. Hysteresis so the state does not flap.
   - Results are stored per snapshot id. Freshness SLOs come from the contract.
5. **Re-evaluation and Quality page.**
   - Scheduled re-evaluation moves products between `certified` and `degraded`.
   - Quality page.

## Out of scope
- Real lineage for the "no lineage" check (025). Presidio or model-based PII detection (038).
- Contract quality rules of type `sql` (custom SQL). They are refused until the parsed SQL guard exists (026).
- Notifications.

## Nav placement
Data > Quality.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Placeholder weights and thresholds are added there for the owner.

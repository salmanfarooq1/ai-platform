# Sprint 025: Lineage and semantic layer. Requirements

Data pillar (M5 Lineage and M4). Every step from source to answer is a lineage edge that links to its decisions. Metrics are defined once and compiled to SQL. That SQL is then rewritten under the grant and guarded before it runs. This is a two-part sprint: part a covers items 1–4, part b covers items 5–8.

Source: old 025, old 026, plus new scope (integration-data-connectors research note).

## Scope
1. **Lineage store.**
   - A new package `lineage/` with a Postgres store: jobs, runs, datasets, edges and facets.
   - Every table has `tenant_id`, RLS and a `GRANT` to `gap_app`, and every query is tenant-scoped.
2. **Ingest OpenLineage events** through the event bus, behind `LineageEmitter`.
   - Sources: pipelines, dlt and dbt (022, including the spooled raw events), client streams and CDC (022), and Direct reads (021) as read edges.
   - Consumers dedupe by CloudEvent `id`.
   - The `LineageLookup` port (`upstream`, `downstream`) arrives here.
3. **Import the client's lineage.**
   - When the client runs OpenMetadata or DataHub, their lineage is imported through the API (023 connection) and marked as "imported".
   - Imported edges never override edges we observed.
4. **Agent facets and redaction.**
   - Facets `agentRun`, `modelCall` and `decisionRecordId`, each with a published JSON Schema in `docs/contracts/lineage/`.
   - Decision ids resolve through `EvidenceLookup` only.
   - SQL literals are never stored, only hashes. The 023 "no lineage" auto-check now reads the store.
   - Data > Lineage page. ADR-0020.
5. **MetricFlow spike first.** `dbt-metricflow` (pin re-checked; 0.15.0 needs dbt-core ≥1.11,<1.13) with dbt-core 1.12.5 and DuckDB 1.5.5.
   - Test against a DuckLake attach and against a Direct source (021).
   - Record the result in `evidence/spike-metricflow.md` and ADR-0021.
   - If it fails, fall back to curated SQL metrics in YAML. The API and the guard stay the same.
   - The dbt Semantic Layer APIs (paid dbt platform) are not used. We use the library only.
6. **Semantic models and metrics** for the reference finance and CRM data: gross margin, revenue and pipeline value, by region and quarter.
   - Each metric has `description`, `owner` and `glossary_term`.
   - `DataAccess` gains `list_metrics`, `describe_metric` and `query_metric(..., snapshot_id, purpose, surface)`.
7. **Compile only, then rewrite, then guard.**
   - MetricFlow produces SQL and never runs it. The 024 rewrite and this guard run next, then the adapter runs it. Filters are typed parameters.
   - The parsed SQL guard allows exactly one SELECT, with a function allowlist. Denied: `read_*`, `glob`, `getenv`, `query`, `query_table`, `COPY`, `EXPORT`, `INSTALL`, `LOAD`, `SET`, `PRAGMA`, `ATTACH`, `CALL`.
   - Every table resolves to a granted relation. An EXPLAIN-based row and cost estimate applies. Over the limit asks for approval (019).
8. **Fuzz corpus and API.** An injection fuzz corpus of 50+ cases in CI. `GET /v1/semantic/metrics` and `POST /v1/semantic/query`. ADR-0021.

## Out of scope
- An external lineage server (Marquez is rejected). Column-level lineage beyond what the events carry.
- User-written metrics or SQL. Agent tools on this path (027).
- Cube Core and Wren AI as the metric path: they enforce their own rules and would bypass the gateway.
- Changed from old 025 and 026: lineage covers reads in place and imported client lineage, and over-limit queries ask for approval.

## Nav placement
- Data > Lineage.
- Workspace > Ask (metrics panel).

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. The spike result is recorded in `planning/DECISIONS.md`.

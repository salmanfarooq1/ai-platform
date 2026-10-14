# Sprint 026: Semantic layer and query guard. Requirements

Vertical slice. Modules: M4 Data Plane (`dataplane/semantic/`), with M1 Gateway for reason codes and the guard verdict in the `query` stage (024).

## Scope
1. **Spike first.** Try `dbt-metricflow==0.15.0` with dbt-core 1.12.5 and DuckDB 1.5.5 against a DuckLake attach.
   - Work on branch `spike/026-metricflow`. Record the result in `evidence/spike-metricflow.md` and in ADR-0021.
   - If it fails, fall back to curated SQL metrics defined in YAML. The API and the guard stay the same.
2. **Semantic models and metrics** for the reference finance and CRM marts:
   - gross margin, revenue, and pipeline value, by region and quarter.
   - Each metric's YAML carries `description`, `owner` and `glossary_term`.
   - The `DataAccess` port (013) gains `list_metrics`, `describe_metric` and `query_metric`, with a `surface` (`api`, `agent`, `dashboard`, `report`, `alert`) in the `data.read` context.
3. **Compile only.** MetricFlow (or the fallback) produces SQL and never runs it.
   - The SQL then goes through the 024 rewrite and the guard, and runs through `QueryEngine`.
   - Filters are typed parameters, never raw strings.
4. **Parsed SQL guard:**
   - Exactly one SELECT.
   - A function allowlist. These are denied: `read_*`, `glob`, `getenv`, `query`, `query_table`, `COPY`, `EXPORT`, `INSTALL`, `LOAD`, `SET`, `PRAGMA`, `ATTACH`, `CALL`.
   - Every table resolves to a granted relation.
   - An EXPLAIN-based row and cost estimate. A query over the limit is a deny. Approval comes in 034.
5. **Fuzz corpus and API.**
   - An injection fuzz corpus of 50+ cases, run in CI.
   - `GET /v1/semantic/metrics` and `POST /v1/semantic/query`.
   - ADR-0021.

## Out of scope
- Approval for over-limit queries (034).
- The agent tools that call this path (027).
- User-written metrics or SQL. Metrics come only from the generated per-tenant project.

## Nav placement
Workspace > Ask (metrics panel).

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. The spike result is recorded as a decision in `planning/DECISIONS.md`.

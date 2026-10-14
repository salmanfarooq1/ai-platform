# Sprint 026: Blueprint
- **Contract:**
  - `GET /v1/semantic/metrics` lists the metrics the caller may query, with their dimensions and allowed filter types. `GET /v1/semantic/metrics/{id}` describes one: description, owner, glossary term, source datasets, dimensions and filter types. Scope: `data:read` (016).
  - `POST /v1/semantic/query` takes `{metrics: [id], group_by: [dimension], filters: [{dimension, op, values}], purpose, snapshot_id?}`. It returns `{columns, rows, sql_sha256, snapshot_id, decision_id, withheld_columns, row_filter_ids}`. `snapshot_id` is one catalog-wide id (016); without it the route pins `DataAccess.current_snapshot`.
  - A deny returns 403 with the reason code. A bad filter is 400 `filter_invalid`. An unknown metric is 404 `metric_not_found`.
  - Refresh the OpenAPI snapshot.
- **Port `DataAccess` (013) grows:** `list_metrics(principal)`, `describe_metric(principal, id)` (description, owner, glossary_term, source_datasets, dimensions, filter types) and `query_metric(principal, MetricQuery, snapshot_id, purpose, surface)`. `surface` is one of `api`, `agent`, `dashboard`, `report`, `alert`. The calling module sets it, never the request body; it goes into the `data.read` context. The routes here pass `api`. Agents (027) and insights (028, 029) call only these methods. The no-op raises `ModuleDisabled`.
- **Metric YAML:** each metric carries `description`, `owner` and `glossary_term`. A metric without them fails project generation.
- **Package:** `dataplane/semantic/`.
  - `compiler.py`: MetricFlow or the YAML fallback, behind one `MetricCompiler` interface.
  - `filters.py`: typed filters.
  - `guard.py`: the parsed guard.
  - `estimate.py`: the EXPLAIN estimate.
- **Pipeline for one query.** Each step's failure is a deny with its own reason:
  1. Compile the metric to SQL.
  2. Bind filters as typed values.
  3. Guard pass 1 on the compiled SQL: parse, one statement, functions, and granted tables.
  4. Run the 024 rewrite.
  5. Guard pass 2 on the rewritten SQL: one statement, allowlisted functions only (the mask functions are in the allowlist), and only rewritten references.
  6. Estimate with EXPLAIN on the locked connection.
  7. `enforce(data.read)`.
  8. Execute on the pinned snapshot.
- **Typed filters:**
  - Each dimension declares a type (`string_enum`, `date`, `int`, `decimal`) and its allowed ops (`eq`, `in`, `between`, `gte`, `lte`).
  - Values are validated against the type and built as sqlglot literal nodes. They are never formatted into text.
  - `in` takes at most `SEMANTIC_FILTER_MAX_VALUES` values (default 100).
- **Guard rules:**
  - The parse uses sqlglot with the duckdb dialect.
  - The root is one query, with CTEs and subqueries allowed if they are queries.
  - Functions are checked against an explicit allowlist in `guard.py` (aggregates, arithmetic, date parts, casts, CASE, COALESCE, and the mask functions). Anything else is denied, including table functions.
  - Every table must resolve through the caller's grants.
- **Estimate:**
  - `SEMANTIC_MAX_ESTIMATED_ROWS` (default 5,000,000 scanned) and `SEMANTIC_MAX_RESULT_ROWS` (default 10,000). Both are validated in `core/settings.py`.
  - These defaults and `SEMANTIC_FILTER_MAX_VALUES` are placeholders, not agreed rules. The Builder logs a question for each in `planning/QUESTIONS.md`.
  - Over a limit: deny `query_over_limit`. Until 034 there is no "approval required" outcome.
- **Gateway:**
  - Reuse the 024 reason codes: `sql_not_parsed`, `statement_not_allowed` (not one SELECT) and `relation_not_granted`. New reason codes in `gateway/reasons.py`: `sql_function_not_allowed`, `query_over_limit`, `filter_invalid` only.
  - The guard verdict travels in the `data.read` action's `context`, like the 024 rewrite outcome. The `query` stage (024) reads it and turns a failed check into a recorded deny. No new stage and no new action kind. A guard deny always writes a decision row.
  - Record v2 extension `query` (024) is extended with `metric_ids` and `estimate_rows`; `sql_sha256` stays as in 024. The snapshot id stays in `data` (016). `surface` is in the `data.read` context.
- **Data:** no migration expected. Semantic models live as YAML in the generated per-tenant project from 019 (`semantic_models/`, `metrics/`). If a table is truly needed, use the next free number after Sprint 025's head.
- **Spike:**
  - Pass means `mf query --explain` compiles gross margin by region and quarter against the DuckLake attach, offline, with `DO_NOT_TRACK=1`, and the SQL runs through the guard.
  - Record the versions, the commands, the output and the decision.
- **UI:** Workspace > Ask, metrics panel.
  - Pick a metric, dimensions and typed filters, then run it.
  - Show the result table, the reason on a deny, and the SQL hash.
  - Follow `.claude/skills/governed-design/SKILL.md`.
- **Tests:**
  - `tests/dataplane/semantic/fuzz_corpus.yaml` (50+ cases) and `test_fuzz_corpus_all_denied`.
  - `test_guard_function_denylist`, with one case per listed function.
  - `test_metric_matches_hand_computed`: expected rows are computed in plain Python from the 015 generator output.
  - `tests/contracts/test_data_access_contract.py` grows: `test_list_metrics`, `test_describe_metric_fields`, `test_query_metric_single_snapshot` on the real adapter, and `ModuleDisabled` on the no-op.
  - `test_surface_set_by_caller` (a `surface` in the request body is ignored), `test_metric_yaml_requires_metadata`, `test_guard_reuses_024_reasons`, `test_query_extension_metric_fields`.
  - `test_over_limit_denied`, `test_filter_values_never_in_sql_text`, `test_guard_runs_after_rewrite`, `test_compiler_contract` (MetricFlow and fallback), `test_deny_writes_decision`.
  - Playwright: `ask-metrics.spec.ts`.
- **Docs:** ADR-0021 (semantic layer first, parsed and guarded SQL second), `docs/architecture.md` (request path steps 4 to 7), the API docs.

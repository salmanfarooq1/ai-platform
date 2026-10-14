# Sprint 026: Threat model
## Assets
- Lakehouse data behind grants: masked columns, row-filtered rows, small groups.
- The locked DuckDB connection and its query budget.
- The compiled SQL and its hash in decision records.

## Trust boundaries crossed
- Caller input (metric ids, dimensions, filter values) into the compiler. In 027 this input comes from an agent.
- Compiler output (SQL) into the guard and the rewrite. MetricFlow is treated as untrusted for grants.
- Guarded SQL into DuckDB.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A filter value carries SQL (`' OR 1=1 --`) | Tampering | Typed filters become literal nodes. They are never formatted into text. | `test_filter_values_never_in_sql_text`, fuzz corpus |
| T2 | Compiled SQL calls `read_parquet`, `glob`, `getenv` or `query` to reach files or settings | Information disclosure | Function allowlist. Table functions are denied. The connection is locked from 016. | `test_guard_function_denylist` |
| T3 | Stacked statements (`; COPY ... TO`, `ATTACH`, `SET`, `PRAGMA`, `CALL`) | Elevation of privilege | Exactly one statement, which must be a query | `test_single_statement_only` |
| T4 | MetricFlow joins a table that the caller has no grant for | Information disclosure | Guard pass 1 resolves every table through the grants | `test_ungranted_join_denied` |
| T5 | The rewrite output is changed or bypassed | Tampering | Guard pass 2 runs on the rewritten SQL. Only rewritten references are allowed. | `test_guard_runs_after_rewrite` |
| T6 | A cartesian join or a huge scan exhausts the worker | Denial of service | The EXPLAIN estimate limit, plus the 016 `memory_limit` and timeout | `test_over_limit_denied` |
| T7 | A guard deny leaves no trace | Repudiation | The `query` stage (024) writes a decision row for every guard deny | `test_deny_writes_decision` |
| T8 | The parser and DuckDB disagree on syntax (parser differential) | Elevation of privilege | Execute the SQL that sqlglot generates, never the original text. Fuzz cases hit known differentials. | `test_executes_generated_sql_only` |
| T9 | The spike tool phones home | Information disclosure | Offline compile, `DO_NOT_TRACK=1`, network guard on in tests | `test_compile_offline` |
| T10 | A caller claims another `surface` to get looser rules later (028, 034) | Spoofing | The calling module sets `surface`; a request body value is ignored | `test_surface_set_by_caller` |

## Abuse cases
- An analyst asks for revenue "by customer" with a filter on one customer, to infer one salary-like value. The 024 minimum group size still applies after the semantic path.
- A crafted metric id or dimension name tries path traversal into the project files. Ids come only from the compiled manifest, and unknown ids return 404.

## OWASP items in scope
- LLM01 (Prompt injection): when 027's agent writes the filters, injected text can only become a typed value. Covered by T1.
- ASI05 (Unexpected code execution): SQL is code. Covered by T2, T3 and T8.
- LLM10 (Unbounded consumption): covered by T6.

## Residual risks
- The EXPLAIN estimate is an estimate. A query under the limit can still be slow. The 016 timeout ends it.
- The function allowlist must be reviewed when DuckDB is upgraded. New functions are denied by default.

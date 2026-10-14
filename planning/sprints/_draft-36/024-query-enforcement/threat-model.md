# Sprint 024: Threat model

## Assets
- Masked and filtered data: the values a grant does not give.
- Small groups that could identify a person.
- Cached results.
- The decision record of every query.

## Trust boundaries crossed
- Analyst SQL (untrusted text) enters the parser and reaches DuckDB.
- Grant state in Postgres controls a query running in the query worker.
- Results move through a shared cache.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | SQL reads a table, file or catalog the grant does not cover | Elevation of privilege | Rewrite every relation; final walk allows only inserted relations; table functions denied | `test_rewrite.py::test_bypass_corpus` |
| T2 | A CTE or alias named like a product table hides an unrewritten read | Elevation of privilege | Scope-aware resolution; final walk | `test_rewrite.py::test_cte_shadowing` |
| T3 | Masked value leaks through a function, cast or join key | Information disclosure | Masks applied inside the replacing subquery, before any user expression | `test_query_enforcement.py::test_mask_not_bypassed` |
| T4 | Small-group inference (group by a unique key, narrow filter) | Information disclosure | `HAVING count(*) >= k` on every grouped SELECT over classified tables | `test_query_enforcement.py::test_small_groups_suppressed` |
| T5 | Time travel to a snapshot before a filter or mask applied | Information disclosure | User `AT`/`VERSION` clauses denied; the rewrite pins the snapshot | `test_rewrite.py::test_time_travel_denied` |
| T6 | Analyst declares a purpose the grant does not have | Spoofing | `purpose` stage, deny on mismatch, purpose recorded | `test_purpose_stage.py::test_mismatch_denied` |
| T7 | Cache serves one user's result to another | Information disclosure | Key includes principal and grant versions | `test_query_cache_isolation.py` |
| T8 | Query keeps running after revocation | Elevation of privilege | Watchdog interrupt; version re-check before return | `test_query_revoke_cancel.py` |
| T9 | Heavy query starves the worker | Denial of service | Sprint 016 timeout, `memory_limit`, `QUERY_MAX_ROWS` | `test_query_enforcement.py::test_limits_apply` |
| T10 | Literals (names, ids) stored in records or logs | Information disclosure | Only hashes stored; logs carry reason codes | `test_query_enforcement.py::test_no_sql_text_stored` |

## Abuse cases
- `SELECT * FROM read_parquet('s3://lake/tenant_b/*.parquet')`. Denied, `relation_not_granted`.
- `WITH invoices AS (SELECT * FROM hr.salaries) SELECT * FROM invoices`. The inner table is not granted; denied.
- `SELECT region, avg(salary) FROM salaries WHERE employee_id = 17 GROUP BY region`. The group has one row; suppressed.

## OWASP items in scope
- OWASP Top 10:2025 A01 Broken Access Control (T1, T2, T5, T8) and A05 Injection (T1, T3).
- LLM02 Sensitive Information Disclosure: this path will serve agents from 027. Masks and k apply to them the same way.
- ASI02 Tool Misuse: the query route becomes an agent tool later; the rewrite is the barrier it will rely on.

## Residual risks
- Differencing attacks across several allowed queries are not fully stopped by k alone.
- Mask defaults are placeholders until the owner confirms them.
- The full function allowlist and cost limits arrive in 026.

# Sprint 026: Acceptance
- [ ] **A1.** All checks pass. The test delta is stated against Sprint 025's report. `check_skips` passes with the allowlist, with no new entries. Evidence: `evidence/checks.txt`.
- [ ] **A2.** The MetricFlow spike result is recorded with versions, commands and output, and the chosen path is named in ADR-0021. Evidence: `evidence/spike-metricflow.md`.
- [ ] **A3.** Every one of the 50+ fuzz cases is denied with a guard reason code, and each deny wrote a decision row. Evidence: `evidence/fuzz-corpus.txt`.
- [ ] **A4.** Gross margin, revenue and pipeline value by region and quarter match the hand-computed result sets exactly. Evidence: `evidence/metric-results.txt`.
- [ ] **A5.** A query over the estimate limit is denied with `query_over_limit` and a clear message, in the API and on the Ask page. Evidence: `evidence/over-limit.txt` and the Playwright run.
- [ ] **A6.** Filter values never appear in the SQL text, and a masked column stays masked after the semantic path. Evidence: `evidence/typed-filters.txt`.
- [ ] **A7.** `DataAccess.list_metrics`, `describe_metric` and `query_metric` pass the contract suite. Each metric has a description, owner and glossary term. A query pins one snapshot id, and its decision has `surface` in context and `metric_ids` and `estimate_rows` in the `query` extension. Guard denies use the 024 reason codes where they exist (`test_guard_reuses_024_reasons`). Evidence: `evidence/data-access-metrics.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** Not applicable: no new compose service. Record the DuckDB `memory_limit` that the estimate test ran under.

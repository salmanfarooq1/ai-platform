# Sprint 022: Threat model

## Assets
- Certification state: consumers and later agents trust certified products.
- Check results, evaluations and the score history.
- Sample rows read for profiling (may hold PII).

## Trust boundaries crossed
- A steward's certification request becomes a gateway decision.
- The worker reads tenant data samples for checks and profiling.
- Contract rules (tenant input) become SQL.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A producer certifies their own product | Elevation of privilege | `duties` stage: requester and owner refused (`separation_of_duties`); `product.certify` only for `data:steward` | `test_duties_stage.py::test_self_certification_denied` |
| T2 | Certification with stale or missing results | Tampering | The `duties` stage needs an evaluation on the current snapshot with no blocking failure | `test_certification.py::test_old_snapshot_evaluation_blocks` |
| T3 | Results edited to turn a fail into a pass | Tampering | Results and evaluations insert-only; evaluation hash in the decision record | `test_quality_tamper.py::test_update_denied`, `test_hash_recorded` |
| T4 | Context facts forged by the caller | Spoofing | `context` built server-side only; request bodies cannot set it | `test_certification.py::test_body_context_ignored` |
| T5 | A contract rule injects SQL | Elevation of privilege | Library rules only; identifiers checked against the schema and quoted; values bound; `sql` type refused | `test_contract_rules.py::test_injection_in_rule_refused`, `test_sql_rule_type_refused` |
| T6 | Profiling copies PII into drafts or results | Information disclosure | Drafts and results hold counts, rates and bounds; accepted-values drafts skipped for classified columns | `test_profiling_drafts.py::test_no_values_from_classified_columns` |
| T7 | Profiling telemetry sends data out | Information disclosure | `YDATA_PROFILING_NO_ANALYTICS=True`; network guard | `test_profiling_drafts.py::test_no_network` |
| T8 | A large sample exhausts worker memory | Denial of service | `QUALITY_PROFILE_SAMPLE_ROWS`; DuckDB `memory_limit` | `test_profiling_drafts.py::test_sample_bounded` |
| T9 | State flaps and floods events | Denial of service | Hysteresis counters | `test_quality_score.py::test_no_flap` |
| T10 | A steward denies having certified | Repudiation | Decision record plus `product_events` row with decision id | `test_certification.py::test_certification_recorded` |

## Abuse cases
- A producer with both `data:write` and `data:steward` moves a product to review and then certifies it. Denied by separation of duties.
- A contract sets `validValues` to `x') OR 1=1 --`. The value is bound as a parameter; the rule just fails.

## OWASP items in scope
- OWASP Top 10:2025 A01 Broken Access Control (T1), A05 Injection (T5), A08 Software and Data Integrity Failures (T3).
- ASI09 Human-Agent Trust Exploitation (early): certification is the trust signal agents will rely on, so it must be honest.
- LLM Top 10: none. No model is called.

## Residual risks
- Regex PII detection misses some PII. Presidio comes in 038.
- Weights and thresholds are placeholders until the owner confirms them.

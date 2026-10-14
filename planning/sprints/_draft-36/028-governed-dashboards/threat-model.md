# Sprint 028: Threat model
## Assets
- Lakehouse data behind grants, now shown to many viewers at once.
- Dashboard specs, which other people trust as "the official numbers".

## Trust boundaries crossed
- Author input (spec, filters, text tiles) into rendering for other viewers.
- Tile results into the browser chart library.
- Agent output (027) into a pinned tile.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A viewer sees data with the author's rights ("share as owner") | Information disclosure | Every tile runs under the viewer's principal and grants. There is no service identity for rendering. | `test_viewer_rights_not_author_rights` |
| T2 | A cached result is served without a decision, or survives a revoke | Information disclosure, Repudiation | No tile cache. The 024 cache sits behind `enforce()` and is keyed by grant version. | `test_cached_tile_still_writes_decision`, `test_grant_revoke_misses_cache` |
| T3 | A spec smuggles SQL, a data URL or a chart expression | Tampering | Schema-validated spec. Charts built server side with inline data, loader off, no user expressions. | `test_tile_spec_rejects_sql_and_urls`, `test_charts_inline_data_only` |
| T4 | A text tile carries script or tracking images | Tampering | Markdown without HTML, no images, links shown as text | `test_text_tile_no_html` |
| T5 | A pinned agent answer carries injected text into an official dashboard | Tampering | Only metric ids and typed filters are kept | `test_pin_answer_keeps_metric_only` |
| T6 | Tiles read different snapshots and show numbers that disagree | Tampering (integrity) | One snapshot id per view, named in every decision | `test_one_snapshot_per_view` |
| T7 | A dashboard with many tiles exhausts the query worker | Denial of service | Tile limit, bounded parallel tiles, view timeout, 026 estimate limit per tile | `test_tile_limit` |
| T8 | Someone edits a published dashboard and denies it | Repudiation | Insert-only versions with spec hash, `dashboard.write` decisions | `test_dashboard_versions_insert_only` |
| T9 | A tenant reads another tenant's dashboard | Information disclosure | RLS on all tables, same 404 body for foreign ids | `test_insights_tenancy` |

## Abuse cases
- Differencing: an analyst builds two tiles whose filters differ by one person, then subtracts. The minimum group size (024) applies to each query. Differencing across queries is a residual risk.
- A steward approves a metric, then the owner changes its formula. The definition hash changes and the certification drops.

## OWASP items in scope
- LLM05 (Improper output handling): covered by T5.
- ASI03 (Identity and privilege abuse): covered by T1.
- LLM10 (Unbounded consumption): covered by T7.

## Residual risks
- Differencing across queries is not fully blocked. Program 3 can add query auditing or noise for sensitive metrics.
- Vega-Lite runs in the browser. Its version is pinned and the loader is off, but a library bug could still matter.

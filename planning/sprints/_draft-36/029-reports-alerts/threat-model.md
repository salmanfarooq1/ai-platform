# Sprint 029: Threat model
## Assets
- Report files in the object store. They hold data after it leaves the query path.
- Recipient lists and alert rules.
- The delivery channel (inbox, SMTP).

## Trust boundaries crossed
- Worker to object store, and object store to the recipient's browser.
- Platform to an SMTP server (optional, off by default).
- Rendered HTML into the PDF engine.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | An author subscribes others and sends them data they may not see | Information disclosure | Each recipient's copy renders under the recipient's grants | `test_report_renders_as_recipient` |
| T2 | Data leaves by email to an outside address | Information disclosure | Recipients must be principals. Email is off by default and carries a link, not data. | `test_recipient_must_be_principal` |
| T3 | The PDF engine fetches a URL (SSRF, tracking) | Information disclosure | WeasyPrint fetcher refuses every URL. Charts are inline SVG. Fonts are local. | `test_pdf_fetcher_refuses_urls`, `test_svg_render_offline` |
| T4 | A shared download link keeps working after a revoke | Information disclosure | Short-lived presigned URLs, and download re-runs `enforce()` | `test_download_rechecks_enforce` |
| T5 | A CSV carries row-level data around the extract rules | Information disclosure | CSV holds only the aggregate tile result from the same `data.read`. Row-level exports stay in 023. | `test_csv_is_aggregate_data_read` |
| T6 | An alert message leaks the value | Information disclosure | Value shown only under the recipient's grant | `test_alert_value_hidden_without_grant` |
| T7 | Alert storms or many subscriptions flood the workers | Denial of service | Dedupe, hysteresis, the job queue limits and the 028 tile limits | `test_alert_hysteresis` |
| T8 | Someone claims a report showed other numbers | Repudiation | Manifest with snapshot ids, decision ids and file hash, bound to the `report.deliver` decision | `test_report_manifest_hash_in_decision` |
| T9 | A tenant reads another tenant's runs or files | Information disclosure | RLS, tenant prefix in object keys, same 404 body | `test_reports_tenancy` |

## Abuse cases
- A leaver keeps getting reports. Their principal is disabled (or stale after 035), so `report.deliver` denies and the run records it.
- A user sets an alert with a tiny threshold on a sensitive metric to learn exact values. The alert value follows the grant, and alerts work only on certified metrics.

## OWASP items in scope
- ASI03 (Identity and privilege abuse): covered by T1 and T4.
- LLM10 (Unbounded consumption): covered by T7.
- Agent items: none. No agent takes part in this sprint.

## Residual risks
- A recipient can still screenshot or forward a PDF they may see. That is a human control, recorded in the receipt.
- WeasyPrint and vl-convert are new native dependencies. They are pinned and scanned, and only run in workers.

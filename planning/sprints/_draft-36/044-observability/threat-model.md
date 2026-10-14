# Sprint 044: Threat model
## Assets
- Spans, logs and metrics, which can carry prompts, answers and identifiers.
- Decision records read by audit analytics.
- The Grafana admin account and dashboards.

## Trust boundaries crossed
- API and worker to the collector (OTLP on localhost and the compose network).
- Collector to the file export and Prometheus; Grafana to Prometheus.
- A client's `traceparent` header into our traces.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Prompt or answer text in span attributes | Information disclosure | Attribute allowlist in-process; collector delete list; content capture off | `test_spans_have_no_canary`, `test_collector_config_deletes_content_keys` |
| T2 | Content in log lines through `extra=` | Information disclosure | Formatter deny list | `test_log_formatter_drops_content_keys` |
| T3 | Content capture turned on in a hosted mode | Tampering | `TELEMETRY_CAPTURE_CONTENT=true` refused outside `local` | `test_settings_refuse_content_capture_in_prod` |
| T4 | Audit analytics shows another tenant | Information disclosure | Rows loaded only through `tenant_connection`; DuckDB has no Postgres access | `test_audit_analytics_cross_tenant` |
| T5 | DuckDB analytics reads files or the network | Elevation of privilege | Locked connection: no external access, config locked | `test_audit_duckdb_external_access_refused` |
| T6 | Grafana with a default admin password | Spoofing | Password required, no default; ports on `127.0.0.1` | `test_compose_grafana_needs_password`, `test_compose_ports_localhost` |
| T7 | A client sends baggage or a forged parent to steer traces | Tampering | Baggage dropped; `traceparent` is only a parent link, never trusted for identity | `test_incoming_baggage_dropped` |
| T8 | High-cardinality labels flood memory | Denial of service | No tenant or product labels; collector `memory_limiter` | `test_metric_labels_bounded` |

## Abuse cases
- A user puts PII in a question and an operator opens the trace. The trace shows ids and outcomes, not the question.
- A tenant admin calls audit analytics with a two-year window. 422 `window_too_large`.

## OWASP items in scope
- LLM02 Sensitive information disclosure (2026): telemetry and logs are the main leak path here.
- LLM10 Unbounded consumption: window caps and DuckDB memory limit.
- ASI08 Cascading failures: the collector being down never fails a request (exporter is async; test `test_request_ok_when_collector_down`).

## Residual risks
- Grafana anonymous Viewer stays on for localhost. Anyone on the machine can read the dashboards. They hold counts only.
- Prometheus series are platform-wide. Per-tenant views live only in audit analytics.
- `local` mode can turn content capture on. Docs say never to do it with real data.

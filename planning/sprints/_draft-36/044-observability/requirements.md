# Sprint 044: Observability. Requirements

Infrastructure plus one page, Kernel. Closes milestone MD (Assurance).

## Scope
1. An OTel collector.
   - `otel/opentelemetry-collector-contrib:0.161.0`, pinned by digest, in compose profile `observability` next to Prometheus and Grafana.
   - The API and the workers export traces to it over OTLP. Job spans continue the trace of the request that queued them.
2. GenAI semantic conventions, opt-in.
   - Behind `OTEL_SEMCONV_STABILITY_OPT_IN`, with the semantic conventions version pinned.
   - Every gateway span carries `decision_id`, so a trace links an answer to its decisions.
3. Grafana dashboards from provisioned files.
   - Decisions and denials, cost, pipeline runs, freshness, quality, approvals waiting.
4. Audit analytics on DuckDB.
   - Over the decision tables, tenant-scoped, hashes and ids only.
   - Shown on the Platform > Observability page.
5. Redaction rules for spans and logs.
   - No prompt, answer, document or SQL text by default, in the app and again in the collector.

## Out of scope
- A trace store and trace UI (Tempo, Jaeger). Traces go to the collector's file exporter here.
- Alerting rules and on-call routing.
- Changes to `/metrics` names from Sprint 008, except new series for the dashboards.

## Nav placement
Platform > Observability.

## Questions this sprint closes
- None.

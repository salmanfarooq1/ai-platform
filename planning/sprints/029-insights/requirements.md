# Sprint 029: Insights. Requirements

Data pillar (M6 Insights). People get governed numbers without asking an agent: a metric catalog, dashboards, reports and alerts. They read on the same metric path as the agent, under each reader's own grants, with a receipt behind every number. A spike tests whether external BI tools can read through the gateway. This is a two-part sprint: part a covers items 1–4, part b covers items 5–9.

Source: old 028, old 029, plus new scope (five-direction review: governed SQL endpoint).

## Scope
1. **The Insights module.**
   - Package `insights/` and the `ENABLED_MODULES` value `insights`. It imports only the kernel and `ports/`.
   - `insights` needs `data`, and startup refuses it alone. The Data edition becomes `gateway,data,lineage,insights`. The module registry and edition smoke script are updated.
   - Tiles read through `DataAccess.query_metric` (025), the same call the agent tools use.
2. **Metric catalog.** Every metric with its plain-words definition, owner, dimensions, source products, freshness, quality score, glossary term and lineage. A metric is "certified" only when its source products are certified (023) and a steward approved its definition hash (`product.certify` decision).
3. **Explore and dashboards.**
   - Pick a metric, dimensions, a time grain, typed filters and a chart type, then save it as a tile.
   - A dashboard is a versioned JSON document (`dashboard_spec` v1) with tiles, layout, filters and a declared purpose. States are draft, published and archived. It exports and imports as a file.
   - Tile kinds: number, line, bar, area, table and text. No raw SQL or chart code.
   - An agent answer (027) can be pinned as a tile. Only its metric ids and filters are kept.
4. **Every number has a receipt.**
   - Each tile reads under the viewer's identity, grants and the dashboard's purpose, never the author's. One view pins one snapshot id.
   - The tile drawer shows the definition, snapshot, decision id, withheld columns, filters, freshness and a verify link.
   - A tile the viewer may not see says "withheld" with the reason. `approval_required` on a tile is a withheld tile, never an approval.
   - No second cache: tiles use the 024 cache behind `enforce()`.
5. **Subscriptions and rendering.**
   - A user subscribes to a dashboard or tile on a schedule (022 scheduler). Formats are in-app, PDF and CSV (table tiles only).
   - Each recipient's copy renders under their own grants. A run is a 020 delegation (`sub` is the recipient, `act` is `job:insights.report.run`) and records `on_behalf`.
   - Rendering happens in a worker, offline: Vega-Lite to SVG with `vl-convert-python==1.9.0.post1`, and HTML to PDF with `WeasyPrint==70.0`. Neither fetches any URL.
6. **Delivery.** The kernel inbox (019) is the default. SMTP is off by default and sends a link, not data. Mailpit is in the optional `mail` profile for development.
7. **Alerts.** One metric, with above, below or percent-change rules. Evaluated on schedule and after `platform.data.snapshot.committed.v1`. The value shows only if the recipient may see it. Dedupe and hysteresis apply.
8. **Report evidence.** A manifest per run (dashboard version, snapshot ids, decision ids per tile, file hash), with its hash in the `report.deliver` decision. A lineage event per run.
9. **Governed SQL endpoint spike.** Can an external BI tool (Power BI or Tableau through a Postgres-wire or Arrow Flight SQL endpoint) read certified metrics through the gateway, under the viewer's own identity, with receipts? Record the result in `evidence/spike-sql-endpoint.md`. If it works, it becomes a candidate for a later sprint. ADR-0031.

## Out of scope
- External BI tools reading the warehouse with their own service account. They would bypass the gateway.
- Recipients outside the platform. Slides or spreadsheet formats beyond CSV. Embedding dashboards in other sites. Alerts on uncertified metrics.
- Changed from old 028 and 029: the inbox comes from 019, report runs use 020 delegation, and the SQL endpoint spike is new.

## Nav placement
Insights > Metrics, Insights > Explore, Insights > Dashboards and Insights > Reports. The inbox bell sits in the header.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Alert thresholds and report retention are placeholders with questions.

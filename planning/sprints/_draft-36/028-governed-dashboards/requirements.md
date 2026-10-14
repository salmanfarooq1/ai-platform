# Sprint 028: Governed dashboards. Requirements

Vertical slice. Modules: new M6 Insights (`insights/`), on top of the M4 semantic layer (026). M1 Gateway records every tile read.

## Scope
1. **The Insights module.**
   - New package `insights/` and `ENABLED_MODULES` value `insights`. It imports only the kernel and `ports/`.
   - Tiles read data through the `DataAccess` port (`query_metric`, 026), the same call the 027 agent tools use.
   - `insights` needs `data`. Startup refuses `insights` without `data`.
   - The Data edition becomes `gateway,data,lineage,insights`. This sprint updates the module registry (013) and `scripts/ci/edition_smoke.sh`.
2. **Metric catalog.**
   - One page that lists every metric from the semantic layer: plain-words definition, owner, dimensions, source products, freshness and quality score.
   - A metric is "certified" only when all its source products are certified (022) and a steward approved its definition.
   - Each metric links to its glossary term (021) and its lineage (025).
3. **Explore.**
   - Pick a metric, dimensions, a time grain and typed filters (026), then a chart type.
   - Save the result as a tile on a dashboard.
4. **Dashboards as versioned documents.**
   - A dashboard is a JSON document (`dashboard_spec` v1) with tiles, a grid layout, dashboard filters and a declared purpose. Tiles read under that purpose (024).
   - Tile kinds: number, line, bar, area, table, text. Users never write raw chart code or SQL.
   - States: draft, published, archived. Each publish makes a new version. Export and import as a file.
   - An ask-your-data answer (027) can be pinned as a tile. Only its metric ids and typed filters are kept, never the model's text.
5. **Every number has a receipt.**
   - Each tile reads under the viewer's own identity and grants, never the author's. Two viewers can see different numbers on the same dashboard.
   - All tiles in one view pin one snapshot (the tenant catalog snapshot), so the numbers agree.
   - A tile drawer shows the metric definition, snapshot id, decision id, withheld columns, row filters, freshness and a link to verify the receipt.
   - A tile the viewer may not see says "withheld" with the reason. The rest of the dashboard still loads.
   - Steward sign-off on a metric is a `product.certify` decision, not a queued approval.

## Out of scope
- A second result cache. Tiles use the 024 query cache, which sits behind `enforce()`.
- Scheduled reports, exports and alerts (029).
- Raw SQL tiles, custom chart code and user-written metrics.
- External BI tools reading the lakehouse. They would bypass the gateway. A governed SQL endpoint for them is a program 3 option.
- Embedding dashboards in other sites.

## Nav placement
New group Insights: Dashboards, Explore, Metrics.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Per-dashboard limits (tiles, queries per view) are placeholders and get new questions.

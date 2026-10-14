# Sprint 025: Threat model
## Assets
- Lineage graph: dataset names, job names, and the edges between tenants' data.
- Facet bodies: SQL templates, model ids, execution ids and decision ids.
- The link from lineage to evidence (decision ids).

## Trust boundaries crossed
- Event bus to the lineage consumer. Events come from platform jobs, but their payloads carry data from dbt and source systems.
- Lineage store to the API and UI, across principals and tenants.
- Lineage module to the evidence core, through `EvidenceLookup` only.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | An event payload names another tenant and writes into its graph | Spoofing | The tenant comes from the platform's CloudEvent context, never from the payload. The insert runs under `tenant_connection`. | `test_payload_tenant_ignored` |
| T2 | A tenant reads another tenant's graph by guessing a node id | Information disclosure | FORCE RLS, `gap_app` only, and 404 with the same body for foreign and unknown | `test_cross_tenant_graph_read_404` |
| T3 | SQL literals (customer names, amounts) leak into stored facets | Information disclosure | Redaction at emit and at ingest. Template plus hash only. | `test_redaction_corpus`, `test_no_literal_in_store` |
| T4 | Column statistics facets carry min, max or sample values | Information disclosure | Keep counts only | `test_column_stats_values_dropped` |
| T5 | A replayed event doubles edges | Tampering | Dedupe by CloudEvent `id` through `processed_events` | `test_duplicate_event_ignored` |
| T6 | A crafted facet `_schemaURL` makes the server fetch a URL | Information disclosure (SSRF) | Schemas are local files. Unknown schema URLs are refused, never fetched. | `test_unknown_schema_url_refused` |
| T7 | Huge or deeply nested events exhaust the consumer | Denial of service | `LINEAGE_EVENT_MAX_BYTES` cap and a depth limit. Refused events are counted. | `test_oversized_event_refused` |
| T8 | A node name with markup runs script in the console | Tampering | Text-only rendering in the graph, with no HTML injection | `lineage.spec.ts` "markup shown as text" |
| T9 | A forged decision id makes lineage look like evidence | Repudiation | Ids are resolved through `EvidenceLookup`. Unresolved ids show "not linked". | `test_unlinked_decision_shown` |
| T10 | A caller of `LineageLookup` (022, 028) walks another tenant's edges | Information disclosure | The real adapter filters by the caller's tenant under RLS; a foreign node returns "not linked". | `test_lineage_lookup_cross_tenant` |

## Abuse cases
- A pipeline author puts a WHERE clause with a salary value into a transform, hoping it shows in lineage. Only the template and hash are stored.
- An operator disables the lineage module to hide a run. Dropped events are counted on `/metrics`, and the decisions still exist.

## OWASP items in scope
- LLM02 (Sensitive information disclosure): through telemetry. Covered by T3 and T4.
- ASI items: none directly. No agent acts in this sprint. Agent facets are passive records that 027 fills.

## Residual risks
- Dataset and job names are stored in clear. A name that itself holds sensitive words is visible to every reader of that tenant's graph.
- Lineage is as complete as the emitters. A job that does not emit leaves a gap, which the `no_lineage` check shows only at product level.

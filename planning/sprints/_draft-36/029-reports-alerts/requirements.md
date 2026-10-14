# Sprint 029: Reports and alerts. Requirements

Vertical slice. Modules: M6 Insights (`insights/`), with the job queue and scheduler (018) and M1 Gateway for delivery decisions.

## Scope
1. **Subscriptions.**
   - A user subscribes to a published dashboard or one tile, on a schedule (the 018 scheduler).
   - Formats: in-app, PDF, CSV (table tiles only).
   - Recipients must be platform principals. Each recipient's copy renders under that recipient's own grants and the dashboard's declared purpose. There is no "send as author".
   - A run acts as the recipient's principal. The decision records `on_behalf` (initiator, subscription, job).
2. **Rendering in a worker.**
   - One run pins one snapshot id, then renders every tile through the 028 path.
   - Charts become SVG offline. HTML becomes PDF offline. Neither fetches any URL.
   - The file goes to the object store under the tenant prefix. Downloads use short-lived presigned URLs from the kernel object store adapter.
   - A CSV holds the aggregate result of a table tile. It is a `data.read`, like the tile. Row-level exports stay with the 023 extracts.
3. **Delivery.**
   - In-app inbox is the default. The inbox is a kernel feature (`core/inbox.py`, `/v1/inbox`), so other modules can post to it.
   - An SMTP adapter is off by default. Email carries a link, not data, unless a setting allows attachments.
   - A local mail catcher runs in an optional `mail` compose profile for development.
4. **Alerts.**
   - A rule on one metric: above, below, or change by a percentage. Thresholds are the owner's input.
   - Evaluated on schedule and after `platform.data.snapshot.committed.v1` (017) for a source dataset of the metric.
   - The message names the metric and the crossing. The value shows only if the recipient may see it.
   - Dedupe and hysteresis stop alert storms. The logic lives in `insights/alerts.py`; it does not import `dataplane`.
5. **Report evidence.**
   - Each run writes a manifest: dashboard version, snapshot ids, decision ids per tile, file hash. The manifest hash is in the `report.deliver` decision.
   - Each run emits a lineage event: inputs are datasets, output is the report.
   - Insights > Reports shows subscriptions, alerts, runs, status, download and receipt.

## Out of scope
- Recipients outside the platform (external emails). Off, and needs a policy decision first.
- Slides or spreadsheet formats beyond CSV.
- Alerts on anything but certified metrics.

## Nav placement
Insights > Reports. New page Workspace > Inbox (kernel, shown in every edition). Sprint 034 posts approval items to it.

## Questions this sprint closes
- None. Retention of report files, alert dedupe windows and attachment policy are placeholders and get new questions.

# Sprint 029: Acceptance
- [ ] **A1.** All checks pass. The test delta is stated against Sprint 028's report. `check_skips` passes with the allowlist, with no new entries. Evidence: `evidence/checks.txt`.
- [ ] **A2.** A weekly finance report subscription with two recipients produces two PDFs. Each one shows only what its recipient may see, and each has its own `report.deliver` decision. Evidence: `evidence/report-recipients.txt`.
- [ ] **A3.** The PDF renders with no network access. The manifest names the dashboard version, snapshots and tile decision ids, and its hash matches the decision. Evidence: `evidence/report-manifest.txt`.
- [ ] **A4.** A CSV of a table tile holds only the aggregate rows the recipient may see, and each run's decisions record `on_behalf`. Evidence: `evidence/csv-and-on-behalf.txt`.
- [ ] **A5.** A gross margin alert fires once after a snapshot commit crosses the threshold, not again inside the dedupe window, and hides the value from a recipient without a grant. Evidence: `evidence/alerts.txt`.
- [ ] **A6.** After a grant is revoked, the next report run withholds the affected tiles. Evidence: `evidence/revoke-next-run.txt`.
- [ ] **A7.** The lineage graph shows the report as an output of the finance datasets, linked to its decisions. Evidence: `evidence/report-lineage.txt`.
- [ ] **A-sec.** The threat-model tests pass. Evidence: `evidence/threat-tests.txt`.
- [ ] **A-mem.** The `mail` profile's memory (docker stats line). Record the PDF render time and peak worker memory for the finance dashboard.

# Sprint 030: Evidence packs and SIEM. Requirements

Gateway pillar (M2 Evidence). An auditor exports a signed evidence pack for one system and one time window, and verifies it offline. The pack carries the technical documents and framework mappings. Decisions also stream to the client's SIEM, and costs are shown per cost centre. This is a two-part sprint: part a covers items 1–4, part b covers items 5–8.

Source: old 042, old 043, the audit-analytics part of old 044, plus new scope (enterprise-gaps-how research note, bundle C).

## Scope
1. **Evidence pack per system and window.**
   - An `ai_systems` table, and a `high_risk` flag that raises the decision retention floor to 183 days. That is a placeholder default (EU AI Act Art. 19 and 26 say at least six months), with a question.
   - Contents: decisions, receipts, log proofs and timestamps, approvals, the oversight log, incidents, a lineage summary, eval results and report manifests. Hashes and ids only, never input text, prompts, answers or SQL literals.
   - Built by a job and downloaded through a short-lived link.
2. **Signed and registered.**
   - The manifest lists every file with its SHA-256 and is signed (COSE_Sign1 with `kid`, from 017).
   - The manifest hash is a `pack` leaf in the transparency log, with an inclusion proof and a timestamp.
   - The pack states the retention in force and whether an external anchor was used.
3. **Offline verification** with the 017 verifier package: signature, file hashes, receipts, chain links in the window, inclusion and consistency proofs, timestamps and the 018 replay of "why allowed".
4. **Audit search and export.**
   - Search decisions by request, decision, run, principal, action, outcome, reason, system and time. Export as CSV or JSON with a row cap.
   - Tenant-scoped audit analytics on DuckDB (hashes and ids only) on the Observability page.
   - The 020 auditor role can use all of this, and nothing that touches row data.
5. **Technical documents and mappings.**
   - A system card in the Annex IV shape, including the Insights `report.deliver` data flow.
   - Model cards and an ML-BOM (CycloneDX) from `models.lock` and the 013 provider register.
   - ISO/IEC 42005 and Art. 27 FRIA templates. A completed assessment is attached by hash.
   - One machine-readable mapping file per framework: EU AI Act Art. 12, 14, 19, 26, 72, 73; ISO 42001 Annex A as a Statement of Applicability; NIST AI RMF and AI 600-1; SP 800-53 tags; OWASP ASI01–ASI10 and LLM Top 10 2026. Each row names the test or document that proves it, and an owner.
   - A release red-team summary (garak, PyRIT, Strix) goes into the pack.
6. **SIEM export.**
   - Audit events are written once as OCSF JSON, with one pinned OCSF version: Authentication (IAM) and API Activity (Application Activity).
   - Fields: time, tenant, actor (user, delegated run id, `act` chain), action, resource, purpose, outcome, policy bundle hash, receipt id, `decision_id`, model identity, source IP. No content text.
   - The OTel collector (028) fans out to Splunk HEC first, then syslog (RFC 5424). CEF is a thin formatter. Sentinel goes through its Logs Ingestion API and is documented, not built.
   - A failed export never fails a decision. The lag is a metric with an alert.
7. **Chargeback and showback.**
   - Every decision record carries `cost_centre`, `tenant`, `agent` and `model`. The cost centre comes from the principal or the agent registry.
   - A per-team showback page with budget alerts.
   - A FOCUS-shaped CSV export with `x_` custom columns that never change the cost totals.
8. **Date checks.**
   - EU AI Act dates in `docs/` are checked against the adopted text on EUR-Lex (Digital Omnibus).
   - The 028 Art. 73 deadlines are compared with the adopted text; a mismatch becomes a question.
   - The Q26 numbers (90-day retention, 10 USD daily cap, 0.02 eval tolerance) each get an owner.

## Out of scope
- Legal advice or a claim of conformity. Pages say "mapped to", never "compliant with".
- Sharing packs outside the platform. A Sentinel connector beyond the documented route.
- Changed from old 042–044: SIEM export and chargeback are new, and audit analytics sits here, with tracing in 028.

## Nav placement
- Evidence > Packs, Evidence > Audit search and Evidence > Frameworks.
- Platform > Exports (SIEM targets and lag).
- Platform > Costs (showback).

## Questions this sprint closes
- Proposes the default for owner question Q-06 (first SIEM): Splunk HEC, with OCSF as the shared shape.

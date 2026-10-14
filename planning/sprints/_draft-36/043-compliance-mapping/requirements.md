# Sprint 043: Compliance mapping. Requirements

A vertical slice in module M2 Evidence: generated documents in packs, mapping tables backed by tests, a Compliance page.

## Scope
1. Technical documents in packs.
   - A system card in the EU AI Act Annex IV shape, generated per system (an `ai_systems` row from Sprint 042).
   - Its data-flow table has a row for Insights: `report.deliver` (dashboard and report data to each recipient, under the recipient's grants).
   - Model cards for the chat, embedding and guard models, from `models.lock` plus a short source file per model.
   - An ML-BOM (CycloneDX) for the same models, with digests from `models.lock`.
2. Templates.
   - An ISO/IEC 42005 impact assessment and an Art. 27 fundamental rights impact assessment (FRIA).
   - A completed assessment attached to a system (`ai_systems`, Sprint 042) goes into its packs, by hash and file.
3. Mapping tables, one machine-readable file per framework.
   - EU AI Act Art. 12, 14, 19, 26, 72, 73. ISO 42001 Annex A as a Statement of Applicability. NIST AI RMF and AI 600-1. SP 800-53 tags. OWASP ASI01–ASI10 and LLM Top 10 2026.
   - Each mapped row names the test or document that proves it, and an owner.
4. OWASP coverage and the release red team.
   - The OWASP matrix collects tests written in earlier sprints. It adds no new control.
   - A release red-team run (garak, PyRIT, Strix) writes a summary that the pack includes.
   - garak `0.17.0` and PyRIT `1.1.0` run in a separate venv or container, outside the main lock.
5. Date check and Q26.
   - A check that EU AI Act dates in `docs/` match the adopted text on EUR-Lex (Digital Omnibus).
   - The Art. 73 report deadlines (`INCIDENT_REPORT_DAYS` from Sprint 039) are compared with the adopted text. They stay settings with defaults; a mismatch is logged as a question, not changed in code.
   - The Q26 numbers (90-day retention, 10 USD daily cost cap, 0.02 eval tolerance) each get an owner.

## Out of scope
- Legal advice or a claim of conformity. The page and docs say "mapped to", never "compliant with".
- New governance controls. A gap found by the matrix goes to `planning/QUESTIONS.md`.
- Observability (Sprint 044).

## Nav placement
Evidence > Compliance.

## Questions this sprint closes
- Q26: each placeholder number gets a named owner role in `planning/DECISIONS.md`.

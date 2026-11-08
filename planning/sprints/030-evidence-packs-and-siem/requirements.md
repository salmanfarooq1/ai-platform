# Sprint 030: Evidence packs and mappings. Requirements

Gateway pillar (M2 Evidence). An auditor exports a signed evidence pack for one system and one time window, and verifies it offline. The pack carries the technical documents and framework mappings. This is a two-part sprint: part a covers items 1–3, part b covers items 4–7.

Source: old 042, old 043, the audit-analytics part of old 044, plus new scope (enterprise-gaps-how research note, bundle C).

Depends on: none.

## Scope
1. **Evidence pack per system and window.**
   - An `ai_systems` table, and a `high_risk` flag that raises the decision retention floor to 183 days. That is a placeholder default (EU AI Act Art. 19 and 26 say at least six months), with a question.
   - Contents: decisions, receipts, external anchor proofs and timestamps, approvals, the oversight log, incidents, a lineage summary, eval results and report manifests. Hashes and ids only, never input text, prompts, answers or SQL literals.
   - Built by a job and downloaded through a short-lived link.
2. **Signed and registered.**
   - The manifest lists every file with its SHA-256 and is signed (COSE_Sign1 with `kid`, from 017).
   - Anchor the manifest hash through the external anchor from 017. The pack includes its proof and timestamp.
   - The pack states the retention in force and whether an external anchor was used.
3. **Offline verification** with the 017 verifier package: signature, file hashes, receipts, chain links in the window, external anchor proof, timestamps and the 018 replay of "why allowed".
4. **Technical documents and mappings.**
   - A system card in the Annex IV shape, including the Insights `report.deliver` data flow.
   - Model cards and an ML-BOM (CycloneDX) from `models.lock` and the 013 provider register.
   - ISO/IEC 42005 and Art. 27 FRIA templates. A completed assessment is attached by hash.
   - One machine-readable mapping file per framework: EU AI Act Art. 12, 14, 19, 26, 72, 73; ISO 42001 Annex A as a Statement of Applicability; NIST AI RMF and AI 600-1; SP 800-53 tags; OWASP ASI01–ASI10 and LLM Top 10 2026. Each row names the test or document that proves it, and an owner.
   - A release red-team summary (garak, PyRIT, Strix) goes into the pack.
5. **Items moved from 018, 019 and 020.**
   - Add the optional OPA runtime adapter (`POLICY_ENGINE=opa`) and the two-engine parity suite. The Python engine stays the default.
   - Add the signed approval webhook and the AuthZEN approval profile.
   - Enforce a tenant IP allowlist in the app and at the 016 proxy. The edge overwrites forwarded headers.
   - Use SPIFFE-format run ids: `spiffe://<trust-domain>/tenant/<tenant_id>/run/<execution_id>`.
   - Run the Keycloak 26.8 token-exchange spike with `actor_token` on a throwaway profile. Build a Keycloak adapter only if nested delegation is no longer a preview feature. Preview features stay out of the default stack.
6. **Incident capture decision.** Decide whether to support opt-in, encrypted, retention-bound prompt and response capture for incident response. It is off by default and needs a DPIA note. Otherwise record a reasoned "will not do" decision.
7. **Date checks.**
   - EU AI Act dates in `docs/` are checked against the adopted text on EUR-Lex (Digital Omnibus).
   - The 028 Art. 73 deadlines are compared with the adopted text; a mismatch becomes a question.
   - The Q26 numbers (90-day retention, 10 USD daily cap, 0.02 eval tolerance) each get an owner.

## Out of scope
- Legal advice or a claim of conformity. Pages say "mapped to", never "compliant with".
- Sharing packs outside the platform. SIEM export, audit search, chargeback and showback (016 and 017).
- Changed from old 042–044: this sprint keeps evidence packs and mappings and receives selected items moved from 018, 019 and 020.
- Re-planned 2026-11-08: see "Re-plan 2026-11-08" in `planning/program/sprint-map.md` and ADR-0035.

## Nav placement
- Evidence > Packs and Evidence > Frameworks.

## Questions this sprint closes
- Resolves the explicit decision on opt-in prompt and response capture for incident response.

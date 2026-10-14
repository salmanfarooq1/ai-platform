# Sprint 042: Evidence packs. Requirements

A vertical slice in module M2 Evidence: contract, backend, console pages, offline verification.

## Scope
1. Evidence pack export per system and time window.
   - Contents: decisions, receipts, log proofs and timestamps, approvals, the oversight log, incidents, a lineage summary, eval results, and the report manifests (Sprint 029) by hash.
   - Records only, as hashes and ids. No input text, prompts, answers or SQL literals.
   - Built by a job; downloaded through a short-lived link from the object store.
2. The pack is signed and registered in the transparency log.
   - The manifest lists every file with its SHA-256 and is signed (COSE_Sign1 with `kid`).
   - The manifest hash is a `pack` leaf in the tenant's log, with its inclusion proof and a timestamp.
   - The manifest carries the anchor warning from Sprint 041 when no external anchor is set.
3. A `high_risk` flag per system.
   - It raises the decision retention floor to 183 days. That number is a placeholder default (EU AI Act Art. 19 and 26 say at least six months) with a question in `planning/QUESTIONS.md`, until an owner confirms it.
   - The pack states the retention in force: days, floor, source.
4. Audit search and export in the console.
   - Search decisions by request id, decision id, run, principal, action, outcome, reason, system and time.
   - Export the result as CSV or JSON, with a row cap.
5. Offline pack verification with verifier v2.
   - Signature, file hashes, receipts, chain links in the window, inclusion and consistency proofs, timestamps.

## Out of scope
- System cards, model cards, ML-BOM and compliance mappings (Sprint 043).
- Telemetry and dashboards (Sprint 044).
- Sharing packs outside the platform (email, portals).

## Nav placement
Evidence > Evidence packs. Evidence > Search.

## Questions this sprint closes
- None. This sprint introduces the `ai_systems` table (no earlier sprint defines a system). Its definition is logged in `planning/DECISIONS.md`. Sprints 043 and 045 use it.

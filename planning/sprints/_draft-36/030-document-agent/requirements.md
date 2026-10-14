# Sprint 030: Document agent. Requirements

Vertical slice. Modules: M3 Agent Runtime (extraction agent) and M4 Data Plane (contract-shaped tables, write path).

## Scope
1. **Docling `2.130.0`, offline.**
   - The model weights and the OCR model are pre-fetched into a volume.
   - Nothing is downloaded at runtime.
   - Only Apache-2.0 weights are used (decided 2026-10-11). The TableFormer weights are dual-tagged CDLA-Permissive-2.0 and Apache-2.0. They are accepted under Apache-2.0 and the ADR records it. If that does not hold, table structure is turned off.
2. **Extraction.** Reference invoices and contracts are extracted into tables shaped by an ODCS contract.
3. **Review queue.**
   - A human approves, edits or rejects each extraction.
   - Approved rows publish through `DataAccess.submit_write`, the port in front of the 017 write path. M3 does not call M4 internals.
4. **Citations.**
   - Each extracted field has a page number and a bounding box.
   - The UI draws them over the page image.
5. **Taint.**
   - Reading document text taints the run.
   - A malicious-PDF test hides instructions to leak data. It shows that nothing leaves and that the tool calls are denied.

## Out of scope
- Formats other than PDF.
- User-defined extraction contracts beyond the two reference contracts (invoice, contract).
- Guard models on document text (038).

## Nav placement
Data > Documents (review queue).

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Record any new ones there.

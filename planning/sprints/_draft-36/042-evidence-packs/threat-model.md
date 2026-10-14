# Sprint 042: Threat model
## Assets
- Evidence packs and audit exports.
- Decision records within the retention floor.
- The receipt signing key (signs the manifest) and the tenant log.

## Trust boundaries crossed
- Console to API (session and CSRF, or bearer).
- Worker to object store; browser to object store through a presigned URL.
- A pack leaving the platform for an auditor's offline machine.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A pack or export carries prompts, answers or PII | Information disclosure | Records only; free text as SHA-256; canary scan | `test_pack_has_no_canary_text`, `test_export_has_no_canary_text` |
| T2 | An exported pack is changed after download | Tampering | Signed manifest with file hashes; log leaf; verifier fails on any change | `test_verifier_rejects_tampered_pack` |
| T3 | Decisions removed from a pack to hide them | Tampering | Chain links checked across the window from the prior checkpoint | `test_verifier_detects_missing_decision` |
| T4 | Admin lowers retention to purge evidence | Tampering | High-risk floor (placeholder default 183 days) inside the SECURITY DEFINER function; flag change is a recorded decision | `test_purge_respects_high_risk_floor`, `test_high_risk_change_recorded` |
| T5 | Another tenant's pack or system is read | Information disclosure | RLS; same 404 for foreign and missing; object key under tenant prefix | `test_pack_cross_tenant_404`, `test_download_cross_tenant_404` |
| T6 | A leaked download link is reused later | Information disclosure | Presigned URL with short TTL; link not logged | `test_download_url_expires` |
| T7 | CSV formula injection in an export | Tampering | Cells starting with `= + - @` are prefixed with `'` | `test_csv_export_escapes_formulas` |
| T8 | A huge window exhausts the worker | Denial of service | `EVIDENCE_PACK_MAX_DAYS`, row cap on export, job timeout | `test_pack_window_too_large`, `test_export_too_large` |
| T9 | A delivered report is later swapped and the pack cannot show what was sent | Repudiation | Report manifests and file hashes in `reports.jsonl`, covered by the signed manifest | `test_pack_includes_report_manifest_hashes` |

## Abuse cases
- A user with `audit:read` but no `admin` tries to flip `high_risk` off before a purge. 403, and the attempt is recorded.
- An auditor gets a pack, then the operator edits a decision row. The verifier fails the chain against the pack's checkpoint.

## OWASP items in scope
- LLM02 Sensitive information disclosure: packs and exports hold hashes and ids only.
- ASI09 Human-agent trust exploitation: approvals and the oversight log in the pack are system records, not agent text.
- ASI10 Rogue agents: actions in the window cannot be dropped from a pack without failing verification.

## Residual risks
- Hashes of short or guessable inputs can be confirmed by brute force. Documented in `docs/contracts/evidence-pack.md`.
- The floor applies to the whole tenant, not only to the high-risk system, because purge follows the tenant chain.
- A pack is only as good as the receipt key. Key handling is Sprint 040's.

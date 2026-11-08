# Sprint 017: Receipts v2 and anchoring. Requirements

Gateway pillar, M2 Evidence upgrade, with a small kernel change for the clock check. The proof that sets us apart comes early: a signed receipt anyone can verify offline.

Source: old 040, old 041, plus new scope (enterprise-gaps-how research note, review.md).

Depends on: 020.

## Scope
1. **COSE_Sign1 receipts and proofs** (RFC 9942) with a `kid` header, in a SCITT draft-compatible signed statement shape.
   - Library: `cbor2` with `cryptography` (or `cwt==3.3.0`). Not `pycose` (stale since 2023). Re-check pin ages (stack.md): a pin under two weeks old is replaced by the previous release.
   - Ed25519 (v1) receipts keep verifying. Later fields (policy hashes in 018, approval in 019, delegation in 020) are record v2 extensions inside the signed payload, so the receipt format does not change again.
2. **Separate keys behind a signing-key port.**
   - One key per role. Startup refuses two roles with the same public key.
   - The file adapter uses secrets mounted as files. Cloud KMS and PKCS#11 adapters, and the live KMS check, move to 031.
3. **Rotation and revocation (Q31).**
   - A dated revocation list, published with the public keys and used by every verifier. A receipt whose record time is at or after `revoked_at` for its `kid` fails. Earlier receipts keep verifying.
   - A runbook with a tested drill: rotate, verify old and new, revoke, verify the cut-off.
4. **Attestation fields** in the record: sandbox image digest, model digest (013), policy bundle hash (filled from 018). Filled where known. A TEE slot is left empty.
5. **One external anchor on by default for client installs.**
   - Adapters: Rekor v2 and a public RFC 3161 authority. `EXTERNAL_ANCHOR` defaults to one of them in the client bundle. The Builder picks it and records why in ADR-0030.
   - Only a hash leaves the host, never tenant data. Dev and CI keep `none` and show a warning. The air-gap bundle (032) sets `none` on purpose and says so in the status answer.
   - Anchor status is part of every checkpoint and status answer. Closes Q29.
6. **Clock pre-flight.** `scripts/preflight.sh` compares the host clock, database clock and external timestamp authority before a stamp. Too much drift refuses the stamp, logs it and shows it in health. Decisions keep working.
7. **Standalone verifier package.**
   - A small installable package with no platform imports. It checks the signature, chain, external anchor proof, key status and revocation list. `scripts/verify/receipt.py` becomes a thin wrapper.
   - Test vectors in the package: valid, tampered, wrong `kid`, rotated, revoked and v1 Ed25519. Policy replay is added by 018.
8. **Verify scripts and ADRs.** ADR-0029 (receipts and keys) and ADR-0030 (external anchoring).
   - Tests: `test_signer_contract`, `test_old_ed25519_receipts_verify`, `test_revoked_key_after_time_fails`, `test_same_key_two_roles_refused`, `test_verifier_has_no_platform_imports`, `test_vectors_pass`, `test_clock_drift_refuses_timestamp`.
9. **Audit search and export.** Search by request, decision, run, principal, action, outcome, reason, system and time. Export results as CSV or JSON with a row cap.
10. **SIEM export.** Write audit events once as OCSF JSON using one pinned OCSF version for Authentication and API Activity. Include time, tenant, actor, action, resource, purpose, outcome, policy package hash, receipt id, `decision_id`, model identity and source IP; never include content text. Export to syslog (RFC 5424) or Splunk HEC without an OTel collector. A failed export does not fail a decision. Measure export lag and alert on it.

## Out of scope
- Evidence packs and compliance mappings (030). Witness networks and gossip between logs. TEE attestation.
- Local TSA, per-tenant transparency log, PKCS#11 and cloud KMS adapters, and the live KMS check (031).
- Data-key encryption and a secrets manager (031).
- A transparency page. Receipts show their log entry in the existing receipt view.

## Nav placement
Evidence > Receipts: look up a receipt, see its format, `kid`, key status, attestation fields, log index and timestamp, and verify it.
Admin > Integrations: the SIEM destination and its export lag, mail and anchor status, each with a test send. Later sprints add their own destinations here (approval webhooks in 030).

## Questions this sprint closes or proposes an answer for
- Q28: the Architect proposes no back-fill, for the owner to confirm. Records from before migration `0009`, and denies whose chain step failed, keep answering 409 `receipt_unavailable`. The Builder builds this and leaves Q28 open.
- Q29: use one public external anchor, RFC 3161 TSA or Rekor, on by default for client installs. Q31: use a dated revocation list.

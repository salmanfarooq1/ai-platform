# Sprint 017: Receipts v2 and anchoring. Requirements

Gateway pillar, M2 Evidence upgrade, with a small kernel change for the clock check. The proof that sets us apart comes early: a signed receipt anyone can verify offline.

Source: old 040, old 041, plus new scope (enterprise-gaps-how research note, review.md).

## Scope
1. **COSE_Sign1 receipts** with a `kid` header, in a SCITT signed statement shape.
   - Library: `cbor2` with `cryptography` (or `cwt==3.3.0`). Not `pycose` (stale since 2023). Re-check pin ages (stack.md): a pin under two weeks old is replaced by the previous release.
   - Ed25519 (v1) receipts keep verifying. Later fields (policy hashes in 018, approval in 019, delegation in 020) are record v2 extensions inside the signed payload, so the receipt format does not change again.
2. **Separate keys behind a signing-key port.**
   - One key per role: receipts, log checkpoints and the timestamp authority. Startup refuses two roles with the same public key.
   - Adapters: file (secrets mounted as files), PKCS#11 (`python-pkcs11` with SoftHSM2 in CI) and one cloud KMS adapter. The KMS adapter is tested with a fake in CI. A live check is a manual step on the first cloud (015).
   - The port is the same seam the data-key KMS port of 031 uses. No data-key work here.
3. **Rotation and revocation (Q31).**
   - A dated revocation list, published with the public keys and used by every verifier. A receipt whose record time is at or after `revoked_at` for its `kid` fails. Earlier receipts keep verifying.
   - A runbook with a tested drill: rotate, verify old and new, revoke, verify the cut-off.
4. **Attestation fields** in the record: sandbox image digest, model digest (013), policy bundle hash (filled from 018). Filled where known. A TEE slot is left empty.
5. **Local transparency log.**
   - One Merkle tree per tenant (RFC 9162 hashing, SHA-256). Leaves are hashes only. Signed checkpoints use the log key, never the receipt key.
   - Inclusion and consistency proofs verify offline. The log accepts receipts now and evidence packs in 030.
6. **Local timestamp authority.**
   - `ghcr.io/sigstore/timestamp-server` (at least `v2.0.6`, pinned by digest) in compose profile `trust`, with `rfc3161-client==1.0.9` on our side. It uses its own key.
   - Chain heads and log checkpoints are timestamped on a schedule.
7. **One external anchor on by default for client installs (changed from old 041, which was off by default).**
   - Adapters: Rekor v2 and a public RFC 3161 authority. `EXTERNAL_ANCHOR` defaults to one of them in the 015 client bundle. The Builder picks it and records why in ADR-0030.
   - Only a hash leaves the host, never tenant data. Dev and CI keep `none` and show a warning. The air-gap bundle (032) sets `none` on purpose and says so in the status answer.
   - Anchor status is part of every checkpoint and status answer. Closes Q29.
8. **Clock pre-flight.** `scripts/preflight.sh` compares the host clock, the database clock and the timestamp authority before a stamp is taken. Too much drift refuses the stamp, logs it and shows it in health. Decisions keep working.
9. **Standalone verifier package.**
   - A small installable package with no platform imports. It checks the signature, the chain, the inclusion proof, the timestamp token, the key status and the revocation list. `scripts/verify/receipt.py` becomes a thin wrapper.
   - Test vectors in the package: valid, tampered, wrong `kid`, rotated, revoked, v1 Ed25519, bad proof. Policy replay is added by 018.
10. **Backups, verify scripts, ADRs.**
   - A backup and restore runbook for the three keys and the log. `poc backup` (015) includes them. Losing them breaks old receipts, and the runbook says so.
   - `scripts/verify/tsa.sh` runs against the live authority, and pytest uses a fake. ADR-0029 (receipts, keys) and ADR-0030 (log and timestamping).
   - Tests: `test_signer_contract`, `test_old_ed25519_receipts_verify`, `test_revoked_key_after_time_fails`, `test_inclusion_proof_offline`, `test_same_key_two_roles_refused`, `test_verifier_has_no_platform_imports`, `test_vectors_pass`, `test_clock_drift_refuses_timestamp`.

## Out of scope
- Evidence packs and compliance mappings (030). Witness networks and gossip between logs. TEE attestation.
- Data-key encryption, a secrets manager and HSM purchase (031).
- A transparency page. Receipts show their log entry in the existing receipt view.

## Nav placement
Evidence > Receipts: look up a receipt, see its format, `kid`, key status, attestation fields, log index and timestamp, and verify it.

## Questions this sprint closes or proposes an answer for
- Q28: the Architect proposes no back-fill, for the owner to confirm. Records from before migration `0009`, and denies whose chain step failed, keep answering 409 `receipt_unavailable`. The Builder builds this and leaves Q28 open.
- Q29: external anchoring, now on by default for client installs. Q31: the dated revocation list.

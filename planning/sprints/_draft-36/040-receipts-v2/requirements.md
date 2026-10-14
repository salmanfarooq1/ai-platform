# Sprint 040: Receipts v2. Requirements

Infra with a small UI change, in M2 Evidence: COSE receipts in a SCITT statement shape, separate keys with rotation and revocation, attestation fields, and an offline verifier that can replay a decision.

## Scope
1. **COSE_Sign1 receipts** with a `kid` header.
   - Library: `cbor2==6.1.5` with `cryptography` (or `cwt==3.3.0`). Not `pycose`.
   - Shaped as a SCITT signed statement.
   - Ed25519 (v1) receipts keep verifying.
2. **Separate keys** for receipts, log checkpoints and the timestamp authority.
   - Secrets are mounted as files.
   - A PKCS#11 adapter slot, tested with SoftHSM.
3. **Rotation and revocation (Q31).**
   - A runbook with a tested drill.
   - Old receipts still verify after a rotation.
   - A receipt signed with a revoked key after its revocation time fails.
4. **Attestation fields** in the record: sandbox image digest, model digest, policy bundle hash. Filled where known. A TEE slot is left empty.
5. **Offline verifier v2** (`scripts/verify/receipt.py`).
   - Checks the signature and the chain.
   - With the policy bundle, replays the decision and compares the outcome.
   - Q28: the Architect's proposal below, for the owner to confirm. ADR-0029.

## Out of scope
- The transparency log, timestamping and external anchors (Sprint 041). This sprint only creates their key slots.
- Evidence packs (Sprint 042).
- TEE attestation. The field exists and stays empty.

## Nav placement
Evidence > Receipts: look up a receipt, see its format, `kid`, key status and attestation fields, and verify it.

## Questions this sprint closes or proposes an answer for
- Q28: the Architect proposes no back-fill, for the owner to confirm. Decisions recorded before migration `0009`, and denies whose chain step failed, keep answering 409 `receipt_unavailable`. Back-filling would sign history the platform did not hash at the time. The Builder builds this proposal and leaves Q28 open in `planning/QUESTIONS.md` until the owner confirms.
- Q31: a dated revocation list, published with the public keys and used by both verifiers.

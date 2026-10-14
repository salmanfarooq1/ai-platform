# Sprint 041: Transparency log and timestamping. Requirements

Infrastructure, module M2 Evidence (upgrade), with a small kernel change for the clock check. No new page.

## Scope
1. A local append-only transparency log for receipts and evidence packs.
   - A Merkle tree per tenant (RFC 9162 hashing, SHA-256). Leaves are hashes only.
   - Signed checkpoints, signed with the log checkpoint key from Sprint 040 (not the receipt key).
   - Inclusion and consistency proofs that verify offline.
2. A local timestamp authority.
   - `ghcr.io/sigstore/timestamp-server` (at least `v2.0.6`; re-check the tag and its date) in compose profile `trust`, pinned by digest.
   - `rfc3161-client==1.0.9` on the client side. The TSA uses its own key from Sprint 040.
   - Chain heads and log checkpoints are timestamped on a schedule.
3. Optional external anchors as adapters, off by default.
   - Rekor v2 and a public RFC 3161 TSA. `EXTERNAL_ANCHOR=none` is the default.
   - The anchor status is part of every checkpoint and status answer, so packs (Sprint 042) can warn when no external anchor is set. Closes Q29.
4. A clock pre-flight.
   - Compare the host clock with the database clock and the TSA time before a timestamp is taken.
   - Too much drift (WSL after sleep) refuses the timestamp, logs it and shows it in health. Decisions keep working.
5. Backups, verify script and ADR.
   - A backup and restore runbook for the three keys and the log. Losing them breaks old receipts; the runbook says so.
   - `scripts/verify/tsa.sh` runs against the live TSA. pytest uses a fake TSA.
   - ADR-0030: local transparency log and timestamping.

## Out of scope
- Evidence packs (Sprint 042). This sprint only gives them the append and proof calls.
- Turning on an external anchor in any default. Witness networks and gossip between logs.
- A transparency UI page. Receipts show their log entry in the existing receipt view only.

## Nav placement
No new page. Evidence > Receipts shows the log index and timestamp of a receipt.

## Questions this sprint closes
- Q29: external anchoring of the chain head. Optional adapters, off by default, with a warning when none is set.

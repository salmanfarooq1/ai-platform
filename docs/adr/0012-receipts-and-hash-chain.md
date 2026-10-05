# ADR-0012: Signed receipts and the decision hash chain

Status: Accepted (Sprint 008)

## Context
Every governed call writes a `gateway_decisions` row. A reader of the audit log must be able to tell that a row is the one the platform wrote, that no row was changed, and that none was removed from the middle. Q7 also asks how long the rows are kept.

## Decision
1. **Hash chain per tenant.** Each row has `chain_position`, `prev_hash` and `row_hash`. `row_hash = sha256(canonical_json(decision record) || prev_hash)`. The first row points at `sha256("genesis:<tenant id>")`. The record holds 13 fields (ids, action, resource, outcome, stage, reason, policy version, input SHA-256, execution id, time). It never holds input text. The trace id is not part of it.
2. **One writer at a time.** The write takes `pg_advisory_xact_lock` for the tenant, reads `chain_heads`, takes its time from the database clock, inserts the row and moves the head, all in the decision transaction. Concurrent writes give one unbroken chain. The lock is held until commit, so decision writes of one tenant are serialized.
3. **Fail closed stays.** If the chain step fails on an allow, the allow becomes a deny `decision_unrecorded` (503). A deny keeps its row: it is stored unchained (null hashes) and the error is logged. A receipt for such a row is refused (409).
4. **Signed receipts.** `GET /v1/receipts/{decision_id}` returns the decision, its chain link and an Ed25519 signature over the canonical JSON of `{chain, decision record}`. The signed text is in the receipt (`canonical`). The server refuses to sign a row that no longer hashes to its own `row_hash` (409 `chain_mismatch`).
5. **Keys.** `RECEIPT_SIGNING_KEY` (base64 of 32 raw bytes) is required in `public-preview` and `prod`. Local mode makes a throwaway key at startup and logs only its `key_id` (first 16 hex of the SHA-256 of the public key). `RECEIPT_PREVIOUS_PUBLIC_KEYS` keeps old public keys listed after a rotation, so older receipts still verify. `GET /v1/receipts/keys` lists public keys only.
6. **Offline check.** `scripts/verify/receipt.py` repeats the few hashing rules on purpose and imports nothing from the platform. It checks a receipt (algorithm, key, signed text, signature, row hash) and a chain (row hashes, links, gaps). A test keeps it in step with `gateway/chain.py` and the server's verify route.
7. **Retention and purge.** Decision records are kept `DECISION_RETENTION_DAYS` (default 90), or a tenant's own `tenants.retention_days`. `gap_app` has no DELETE, so a narrow SECURITY DEFINER function (`decisions_purge_batch`, pinned `search_path`, revoked from PUBLIC) does it. It refuses any tenant but the one in `app.tenant_id` and computes the cutoff itself with a hard floor of 30 days, whatever the caller or the tenant passes. `gap_app` cannot insert into `chain_checkpoints`: the function writes the row. The worker first asks `decisions_purge_plan` what it would purge, signs (tenant, position, row_hash, reason) with the receipt key, and passes the signature; the function recomputes the plan in the same transaction and refuses a checkpoint that is unsigned or is not the one it computes. Then it deletes the oldest expired chained rows, up to the first row that is not expired. Genesis (position 0) is derived from the tenant id and needs no row or signature. Verification rejects an unsigned or badly signed purge checkpoint. Unchained rows expire by age. The job kind `purge_decisions` runs it in batches and writes `platform.gateway.purge.v1` to the outbox in each batch transaction. A scheduler in the worker queues one job per tenant per UTC day (idempotency key), only for tenants that have expired rows. Verification starts at the checkpoint just before the first remaining row.

## Consequences
- The chain is tamper evident, not tamper proof. Someone with owner rights on the database could rewrite a whole chain consistently. Receipts that were already issued still fail against a rewritten chain, so keep them. Anchoring the head hash outside the database is not built.
- A key that signs receipts is a secret to protect. Losing it does not break the chain, only new signatures.
- Rows written before migration `0009` have no chain link. They get no receipt and expire by age.
- Serializing decision writes per tenant caps one tenant's decision rate at the speed of one transaction. Tenants do not block each other.
- Cost: an unpriced model is costed at the highest known rate, and a hosted mode refuses to start when a configured chat or embedding model has no price. The cap is checked before a call and booked after it, so concurrent calls can each overshoot it by one call.
- Metrics and the cost cap ship in the same sprint but are separate decisions (see `planning/DECISIONS.md`).

## Accepted risks
- **Cross-tenant reads by the app role (QA L1).** `retention_due_tenants`, `trust_jobs_by_status` and `trust_outbox_lag` return tenant ids, counts and one age to any `gap_app` session. They return no row content, and the worker and the metrics endpoint need them.
- **Old public keys cannot be revoked (QA L3).** A key listed in `RECEIPT_PREVIOUS_PUBLIC_KEYS` stays valid for every receipt it signed. Revocation is Q31.
- **The eval baseline can change with the code (QA L4).** A change to `scripts/eval/baseline.json` shows as a diff in review. Branch protection that requires that review is a hosting setting, and hosting is parked.
- **A deny can lose its row on a broken connection (QA L6).** If the connection itself fails, the deny is not recorded and the error propagates, so the call fails. This is unchanged from before Sprint 008.

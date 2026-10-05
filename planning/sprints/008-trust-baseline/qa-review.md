# Sprint 008: QA and code review

The QA agent returned this as text, and the Architect saved it. The QA agent ran 79 targeted tests, and all passed.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass (Architect) | Full re-run by the Architect, see the sign-off |
| A2 | pass | The verify route uses only the server keyring. The chain lock is per tenant and transaction-scoped. Fail closed holds. See M1. |
| A3 | pass with findings | M2, L1 |
| A4 | pass | A mutation fails the gate. CI has an `eval-gate` job. See L4. |
| A5 | pass with finding | M3 |
| A6 | pass with finding | M4 |
| A7 | pass (Architect) | Playwright |

## Findings
**High:** none.

**Medium**
- **M1:** the app role can insert unsigned checkpoints, so a compromised app could delete a run of rows behind a forged checkpoint.
- **M2:** `decisions_purge_batch` takes the default retention from the caller, so a caller can purge its own tenant down to one day.
- **M3:** an unpriced model costs $0, so it never trips the cost cap.
- **M4:** the `method` label on `/metrics` takes any HTTP method, so the series can grow without limit (unauthenticated).

**Low**
- **L1:** `retention_due_tenants` and the `trust_*` functions return cross-tenant ids and counts to any `gap_app` session.
- **L2:** `RECEIPT_SIGNING_KEY` is a plain `str` in Settings.
- **L3:** old public keys cannot be revoked.
- **L4:** the eval baseline can be changed in the same change as the code.
- **L5:** the Trust UI may label unsigned fields as verified.
- **L6:** a deny whose chain step fails on a broken connection loses its row, as it did before Sprint 008.

## Architect disposition
**Builder fixes, each with a test**

| Finding | Fix |
|---|---|
| M1 | Checkpoints are written only through a `SECURITY DEFINER` function, and `gap_app` loses INSERT on `chain_checkpoints`. Each checkpoint carries a signature over (tenant, position, row_hash, reason) made with the receipt key. Verification rejects an unsigned or badly signed checkpoint. |
| M2 | The function enforces a hard floor of 30 days, whatever the caller passes. Record it in DECISIONS. |
| M3 | An unpriced model is costed at the highest known rate. In hosted modes, startup fails if a configured chat or embedding model has no price. Document that concurrent calls can overshoot the cap by one call each. |
| M4 | Methods outside the standard set are labelled `OTHER`. |
| L2 | Use `SecretStr`. |
| L5 | Only fields that the signature covers are shown under "Verified". Other fields are labelled as context. |

**Accepted and documented in ADR-0012**

| Finding | Reason |
|---|---|
| L1 | The functions return ids and counts only, for the worker and the summary. |
| L3 | Key revocation becomes Q31. |
| L4 | A baseline change shows in review as a diff to `baseline.json`. Branch protection is a hosting setting (parked). |
| L6 | It's unchanged from before Sprint 008: the error still propagates and the call fails. |

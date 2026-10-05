# Sprint 010: QA and code review

The QA agent returned this as text, and the Architect saved it.
- It ran 149 targeted tests, and all passed.
- It did not re-run the live run. It read the evidence instead: 16 live Redpanda tests passed.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass | Contract suite on the fake and live |
| A2 | pass | A relay crash between ack and mark gives a duplicate, which dedupe absorbs |
| A3 | pass, with H1 | |
| A4 | pass | One node only, labelled as such |
| A5 | pass | No migration was added |

## Findings
**High**
- **H1:** a failed dead-letter send, or a failed commit, lets the next record's commit cover the failed record. The poison record is then lost.

**Medium**
- **M1:** `x-error` and the warning log carry `str(exc)`, which may hold secrets or input text.
- **M2:** the relay skips a failed or locked row and still sends later rows for the same tenant. Per-tenant order then breaks.
- **M3:** the fake can't model "the send applied, but the ack was lost".

**Low**
- **L1:** the live run checks redelivery more weakly than the fake does.
- **L2:** the relay holds a row lock while it waits a long time for the broker ack.
- **L3:** the Redpanda image is pinned by tag, not by digest.
- **L4:** with no key, the fake picks a partition differently from Kafka.
- **L5:** a possible missed wake-up in the fake (test latency only).

## Architect disposition
**Builder fixes, each with a test**

| Finding | Fix |
|---|---|
| H1 | Any failure in handling rewinds the partition to the failed record (`seek`, added to the consumer protocol and the fake) before the next poll. Test: the dead-letter send fails once, and the record still reaches the DLQ. Fix the docstring, the runbook and the ADR. |
| M1 | `x-error` holds only the exception class and a short code. The log keeps the detail without `exc_info` text from the payload. Test with an exception that carries a secret. |
| M2 | Per tenant, the relay stops that tenant's batch at its first failed or locked row. Later rows for that tenant wait for the next pass. Test: event 1 fails once and is still delivered before event 2. |
| M3 | Add a fake mode where the send is applied and then raises. Test that the retry's duplicate is absorbed. The docs say ordering relies on sequential sends. |
| L1 | State it in the report and the runbook. |
| L2 | Set short producer request and delivery timeouts in settings, with defaults. |

**Accepted:** L3 (the runbook says to pin by digest on first pull), plus L4 and L5 (they affect test fidelity only and are noted).

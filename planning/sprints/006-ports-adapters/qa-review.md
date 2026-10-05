# Sprint 006: QA and code review

The QA agent returned this as text, and the Architect saved it. Evidence: `evidence/qa-ports.txt`, `qa-grep-imports.txt`, `qa-ui-runs.txt`.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass | ruff and mypy clean on 110 files, DDL guard OK |
| A2 | pass | The suites QA ran pass. The only skips are live MinIO. Architect full run: 1084 passed, 10 skipped |
| A3 | pass | No SDK imports in `api core gateway` |
| A4 | pass for 7 of 8 | AgentRuntime has one adapter until 007 and 009 |
| A5 | pass | See M3 |
| A6 | not re-run | The stale-vector e2e test passes |
| A7 | partly checked | The ADRs exist |
| A8–A10 | pass | |
| A11 | pass | Architect: 167 Vitest, 71 Playwright |

## Findings
**High:** none.

**Medium**
- **M1:** a bus that raises on a deny also rolls back the deny's audit row (`gateway/record.py`).
- **M2:** migration 0007 sets NOT NULL, so an old image can't insert after it runs (Q17).
- **M3:** the 0007 backfill uses the configured dimension, not the real vector width.

**Low**
- **L4:** the in-process bus swallows subscriber errors. This is documented, and it's revisited in 007.
- **L5:** two network-guard tests no longer patch `litellm`.
- **L6:** the CI skip check is too loose.
- **L7:** the session routes are exempt from the auth sweep test with no explicit guard on the exemption list.
- **L8:** the run store is bounded and in memory. Accepted.
- **L9:** the lab scripts are outside the import lint. Document it.
- **L10:** `resource` is client-chosen but checked. Accepted.

## Architect disposition
- **Builder:** M1, M2 (runbook), M3, L5, L6, L7 and L9.
- **Accepted:** L4 (until 007's outbox), L8 and L10.
- **M1 rule:** a decision row is never lost because of the bus. An allow with a failed publish still fails closed with 503. A deny keeps its row and stays denied.

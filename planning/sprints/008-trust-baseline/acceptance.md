# Sprint 008: Acceptance
- [x] **A1.** All backend and frontend checks pass with 0 skipped.
- [x] **A2.** Receipts: a valid receipt verifies offline. A tampered decision, signature or chain link fails verification. Evidence: `receipts.txt`
- [x] **A3.** Retention: the purge removes only expired rows of the right tenant, and chain verification passes across the checkpoint. Evidence: `retention.txt`
- [x] **A4.** The eval gate fails CI when the baseline drops: a mutation test lowers a fake score and the gate fails. Evidence: `eval-gate.txt`
- [x] **A5.** The cost breaker returns 429 `cost_cap_exceeded` with a deny row, and fails closed if Redis is down. Evidence: `cost-cap.txt`
- [x] **A6.** `/metrics` exposes the listed series. The compose profile file is valid (`docker compose --profile observability config`). Grafana and Prometheus running is "not verified here" if image pulls fail, with `scripts/verify/observability.sh`. Evidence: `metrics.txt`
- [x] **A7.** Playwright: open Trust, verify a receipt (valid), then a tampered one (invalid). Axe is clean. Evidence: `playwright.txt`

## Sign-off
Sprint 008 is accepted. The Architect re-ran the checks after the QA fixes:
- ruff, mypy and the DDL guard are clean.
- Backend: 1294 passed. The only skips are the 10 live-MinIO runs.
- 192 Vitest tests and 77 Playwright tests passed.

QA findings and their outcomes are in `qa-review.md`.

The Architect added one note to `.env.example`: a separate worker process must share `RECEIPT_SIGNING_KEY` with the API.

# Sprint 008: Acceptance
- [ ] **A1.** All backend and frontend checks pass with 0 skipped.
- [ ] **A2.** Receipts: a valid receipt verifies offline. A tampered decision, signature or chain link fails verification. Evidence: `receipts.txt`
- [ ] **A3.** Retention: the purge removes only expired rows of the right tenant, and chain verification passes across the checkpoint. Evidence: `retention.txt`
- [ ] **A4.** The eval gate fails CI when the baseline drops: a mutation test lowers a fake score and the gate fails. Evidence: `eval-gate.txt`
- [ ] **A5.** The cost breaker returns 429 `cost_cap_exceeded` with a deny row, and fails closed if Redis is down. Evidence: `cost-cap.txt`
- [ ] **A6.** `/metrics` exposes the listed series. The compose profile file is valid (`docker compose --profile observability config`). Grafana and Prometheus running is "not verified here" if image pulls fail, with `scripts/verify/observability.sh`. Evidence: `metrics.txt`
- [ ] **A7.** Playwright: open Trust, verify a receipt (valid), then a tampered one (invalid). Axe is clean. Evidence: `playwright.txt`

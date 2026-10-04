# Sprint 004: Acceptance

Evidence goes in `evidence/`.

- [ ] **A1.** ruff, mypy, `check_no_ddl` and unit tests: 0 failed. Evidence: `ruff.txt`, `mypy.txt`, `pytest-unit.txt`
- [ ] **A2.** int+e2e: 0 failed, 0 skipped. All Sprint 002–003 tests still pass with their assertions unchanged, except for the documented moves. Evidence: `pytest-int-e2e.txt`
- [ ] **A3.** Each requirement 1–10 and each of e2e scenarios 1–9 maps to named tests (table in `report.md`).
- [ ] **A4.** `grep -n "RateLimitMiddleware\|TokenBudgetMiddleware" api/main.py` finds nothing. The import-lint test exists and passes. Evidence: `grep-middleware.txt`
- [ ] **A5.** Live run with two tenants and different policies, using curl: allowed (200), denied by KB (403), denied by model (403). psql shows the matching `gateway_decisions` rows with `policy_version` and a 64-char `input_hash`, and no query text anywhere in the table (grep a pg_dump of that table for the query string: 0 hits). Evidence: `live-curl.txt`, `decisions-psql.txt`
- [ ] **A6.** The fail-closed test is parametrized across every stage and passes. Evidence: test names in `pytest-unit.txt`
- [ ] **A7.** Property test for narrowing runs ≥ 200 examples. Evidence: hypothesis statistics output
- [ ] **A8.** Migration 0005 is applied on a DB at 0004 that holds data, with no data loss. Evidence: `migrate.txt`
- [ ] **A9.** ADR-0006 written. Docs updated (`ARCHITECTURE.md`, `AGENTS.md` if commands changed, `CHANGELOG.md`, `STATE.md`). OpenAPI snapshot refreshed. No secrets in the diff.

## Sign-off
Sprint 004 is accepted. The Architect re-ran the checks:
- 709 passed, 0 skipped
- ruff and mypy clean (81 files)
- DDL guard OK

The QA findings and their outcome are in `qa-review.md`.

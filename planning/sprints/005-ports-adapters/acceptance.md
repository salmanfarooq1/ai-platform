# Sprint 005: Acceptance

- [ ] **A1.** ruff, mypy (strict on `ports/` and `adapters/`), DDL guard, unit tests: 0 failed. Evidence: `ruff.txt`, `mypy.txt`, `pytest-unit.txt`
- [ ] **A2.** int+e2e+contracts: 0 failed, 0 skipped (except a documented MinIO skip, if the image can't be pulled). Every earlier test still passes with unchanged assertions. Evidence: `pytest-int-e2e.txt`
- [ ] **A3.** `grep -rn "import litellm\|langchain_litellm\|import redis\|from redis" api core gateway` finds nothing. The import-lint test passes. Evidence: `grep-imports.txt`
- [ ] **A4.** Each port has a contract suite, run against ≥ 2 implementations. Evidence: test ids in `pytest-int-e2e.txt`
- [ ] **A5.** Migration 0006 on data: counts are kept, and every row has a model and dimension. Evidence: `migrate.txt`
- [ ] **A6.** Live run: ingest, then search, works. Change `EMBED_MODEL`, restart, and search finds none of the old chunks while `/v1/health` shows `stale_vectors > 0`. Evidence: `live-stale.txt`
- [ ] **A7.** ADR-0007 and the docs are updated. OpenAPI snapshot refreshed (health field). No secrets.
- [ ] **A8.** `report.md` has a requirement → tests table, and lists every moved function (from → to).

# Sprint 003: Acceptance

Evidence goes in `evidence/`.

- [x] **A1.** ruff passes, mypy passes, and unit tests show 0 failed. Evidence: `ruff.txt`, `mypy.txt`, `pytest-unit.txt`
- [x] **A2.** `pytest -m "integration or e2e" -rs`: 0 failed, 0 skipped. The app connects as the non-superuser `gap_app`. Evidence: `pytest-int-e2e.txt`
- [x] **A3.** Every requirement 1–11 has at least one named test. Evidence: a table in `report.md` mapping requirement → test names.
- [x] **A4.** psql as `gap_app` with no `app.tenant_id` set: `select count(*)` on each tenant table returns 0. As the owner, rows exist. Evidence: `rls-psql.txt`
- [x] **A5.** Starting the app with a superuser `DATABASE_URL` fails with a clear message. Evidence: `startup-guard.txt`
- [x] **A6.** Migration on a DB holding 0001-era data: `0001` → `0002` keeps the row counts and backfills `tenant_id`. Evidence: `migrate-existing.txt`
- [x] **A7.** Live run with curl: no token → 401. Tenant A's key ingests and searches successfully. Tenant B's key gets no A data. A spoofed header changes nothing. Evidence: `live-curl.txt`
- [x] **A8.** The admin CLI creates a tenant, principal and key, and revokes the key. The secret is printed once and only its hash is stored (psql shows the hash). Evidence: `admin-cli.txt`
- [x] **A9.** `grep -rn "NAMESPACE_REGISTRY" api core config.py` finds nothing. No route reads a tenant from request input (grep for `tenant_id` in the routers shows only principal-derived use). Evidence: `grep-tenant.txt`
- [~] **A10.** The UI build passes. `nginx.conf` sets the Authorization header from env, and no key appears in `ui/dist`. Evidence: `ui-build.txt`, `ui-dist-grep.txt`
- [x] **A11.** No secrets in the diff. Docs are updated (`AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md` data and API sections, `CHANGELOG.md`, `STATE.md`). `report.md` holds the hosted migration steps.

## Architect sign-off
Re-ran ruff, mypy, the DDL guard and the full suite: 492 passed. Re-ran QA M1 by hand: denied. QA found no isolation break in 76+ attacks.
Open: A10 nginx rendering and the image build (sandbox). Hosted steps are in report §8.

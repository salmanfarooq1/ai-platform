# Sprint 005: Frontend foundation and showcase. Report

The backend and frontend Builders returned their reports as text. The Architect saved this summary and re-ran every check.

## 1. Acceptance
| Check | State | Evidence |
|---|---|---|
| A1 ruff, mypy, DDL guard, full suite | done | `backend-*.txt`. Architect re-run: 805 passed, 0 skipped, mypy clean on 88 files |
| A2 web edge | done | `web-edge.txt` |
| A3 console endpoints | done | `console-api.txt` |
| A4 OpenAPI and generated client, `tsc` | done | `frontend-typecheck.txt` |
| A5 ESLint and Vitest | done | `frontend-unit.txt` (34 tests) |
| A6 Playwright allow and deny across the real API | done | `playwright.txt`, `architect-playwright.txt` (36 passed) |
| A7 landing lazy-load and reduced motion | done | `landing.txt` |
| A8 Lighthouse desktop ≥ 85 | done here | `lighthouse.json` (99). `scripts/verify/lighthouse.sh` re-runs it locally |
| A9 axe in both themes | done | `axe.txt` (0 violations) |
| A10 parity, then removal | done. The image build is **not verified here** | `parity.txt` |
| A11 docs, no em-dash, no "demo" | done | `docs-grep.txt` |
| A12 frontend CI | done. It has **not run on GitHub** | `.github/workflows/frontend.yml` |

## 2. What changed
- **Backend:**
  - `api/web_edge/` holds the session store, routes and cookie auth. `api/middleware/auth.py` adds cookie auth after bearer, plus CSRF.
  - Migration `0006` adds `auth_lookup_preview`.
  - Scope `audit:read`, action `audit.read`.
  - `api/routers/console.py`, `api/models/console.py`, `api/services/cursor.py`, and `scripts/e2e/serve.py` for Playwright.
- **Frontend:**
  - `ui/` was rebuilt in strict TypeScript. The source is in `src/app`, `src/api` (generated `schema.d.ts`), `src/features`, `src/components`, `src/landing` and `src/styles`.
  - `ui/e2e/` holds the Playwright specs.
  - The old JavaScript UI and the nginx preview-key injection are removed.
- **Docs:** ADR-0007, `docs/UI_GUIDELINES.md` 2.0.0, the README UI section, AGENTS, ARCHITECTURE, and hosting files that no longer mention `PREVIEW_API_KEY`.
- **Design:** `.claude/skills/governed-design/` (the project skill plus the vendored MIT taste-skill files).

## 3. Tests
- **Backend:** 709 tests before, **805 after**, with 0 failed and 0 skipped.
- **Frontend:** 34 Vitest and 36 Playwright tests. Lighthouse scores 99 and axe reports 0 violations.

## 4. Approved deviations
These are listed in `blueprint.md` §6:
- migration `0006`
- the `principal` filter name
- nullable principal fields
- the stricter CSRF method rule
- the session stores the public key prefix, so a revoked key ends the session

## 5. QA follow-ups (`qa-review.md`)
- **M1 and M2:** fixed with tests.
- **L1–L4:** fixed with tests.
- **M3:** parked as Q12 (hosting).
- **Flaky Playwright filter test:** the Architect fixed it with retrying assertions. The test is just as strict, and it passed 3 runs in a row and the full suite.
- **`scripts/e2e/serve.py`:** now cleans up leftover test databases from killed runs.

## 6. Decisions and deferred costs
- **shadcn and third-party sources:** the shadcn registry, 21st.dev and threeui.com are blocked here (Q11), so the components are hand-built on Radix with their source noted in comments.
- **Insights page:** not carried over. Usage replaces analytics.
- **Agent runs page:** built from decisions grouped by request until a runs API exists (Sprints 006 and 007).
- **History:** kept in the browser's localStorage and cleared on sign-out.
- **Accepted risks:** S5-1 and S5-2, recorded in `planning/RISKS.md`.

## 7. Not verified here
- The UI Docker image build.
- The CI workflow running on GitHub.
- Behaviour behind a hosting proxy (Q12).

## 8. Commit blocks
These are in `planning/COMMIT_PLAN.md` under Sprint 005. They rebuild this sprint's exact file state from a saved git tree snapshot, so later sprints in the same working tree don't leak into these commits.

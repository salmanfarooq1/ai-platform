# Sprint 005: Acceptance

The sprint is done only when every check passes and the Architect has re-run it.

| # | Check | Evidence |
|---|---|---|
| A1 | ruff, mypy, DDL guard and the full pytest suite pass with 0 skipped | `evidence/backend-*.txt` |
| A2 | Web edge tests pass. Each one below has a test. | `evidence/web-edge.txt` |
| A3 | Console endpoints are covered. Each of the cases below has a test. | `evidence/console-api.txt` |
| A4 | The OpenAPI snapshot is updated, the client is generated from it, and `tsc --noEmit` is clean | `evidence/frontend-typecheck.txt` |
| A5 | ESLint is clean and Vitest passes, with component tests for the verdict badge, trace timeline, receipt, decisions table states (loading, empty, error) and sign-in form | `evidence/frontend-unit.txt` |
| A6 | Playwright passes against the real API (with fakes) and real Postgres and Redis. Both cases below run. | `evidence/playwright.txt` |
| A7 | The landing page is lazy-loaded. Its checks are listed below. | `evidence/landing.txt` |
| A8 | Lighthouse desktop performance is ≥ 85 on the landing page | `evidence/lighthouse.json`, or "not verified here" plus `scripts/verify/lighthouse.sh` |
| A9 | Accessibility is checked with axe (via `@axe-core/playwright`) on Ask, Decisions and the landing page, in both themes, with 0 serious or critical violations | `evidence/axe.txt` |
| A10 | Parity: Ask, Library and System work in the new UI. Then the old JS UI files and the nginx key injection are removed, and the UI Dockerfile builds the new app (or "not verified here") | `evidence/parity.txt` |
| A11 | Docs are updated, with no em-dashes in UI copy and no "demo" wording | `evidence/docs-grep.txt` |
| A12 | CI runs the frontend jobs: lint, tsc, vitest, build and Playwright | `.github/workflows/*` diff |

## A2: web edge tests
- A bad key gives 401.
- The cookie flags are right.
- The session holds no key material.
- An unsafe method without CSRF gives 403.
- A preview session has no `kb:write` or `admin`.
- Preview is 404 outside `public-preview` mode.
- Logout clears the session.
- A bearer token still works.
- A session for tenant A never sees tenant B.

## A3: console endpoint tests
- Filters and the cursor work.
- A foreign decision id gives a 404 identical to a missing one.
- Responses carry no secret or hash, checked by grepping the response.
- A missing `audit:read` scope gives 403 and a deny row.
- Each read writes an `audit.read` allow row.
- RLS holds as `gap_app`.

## A6: Playwright cases
- **Allow:** sign in → ask a question → open that call in the Decisions explorer → see the allow verdict and the policy version.
- **Deny:** a request denied by policy shows the deny verdict and its reason code.

## A7: landing page checks
- The WebGL chunk is separate and loads after first paint.
- With reduced motion, there's no GSAP animation and the poster is shown.
- No WebGL is in any `/app` chunk. Check this with a build-output grep.

## Sign-off
Sprint 005 is accepted. The Architect re-ran the checks: 805 backend tests passed, 0 skipped. ruff and mypy are clean. 34 Vitest and 36 Playwright tests passed. Two items are not verified here: the image build and CI on GitHub. QA findings and their outcomes are in `qa-review.md`.

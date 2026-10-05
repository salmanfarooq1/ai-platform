# Sprint 005: QA and code review

The QA agent returned this as text, and the Architect saved it. The re-run output is in `evidence/qa-rerun.txt`.

## Acceptance
| # | Result | Note |
|---|---|---|
| A1 | pass | Re-run: 791 passed, 0 skipped. ruff, mypy and the DDL guard are clean. |
| A2 | pass | All 9 cases are tested. CSRF method and content-type tricks were probed by hand, and none bypassed it. |
| A3 | pass | All 6 cases are tested. See M1 for crafted cursors. |
| A4 | pass | `tsc` exits 0. |
| A5 | pass | Component tests are green. |
| A6 | pass | The allow and deny cases pass. |
| A7 | pass | WebGL and GSAP are only in landing chunks. Reduced motion loads neither. |
| A8 | Builder evidence only | 99, from the Builder's run. QA didn't re-run it. |
| A9 | Builder evidence only | 0 axe violations, from the Builder's run. QA didn't re-read it. |
| A10 | pass, with one gap | The UI Docker image wasn't built (sandbox). |
| A11 | pass | |
| A12 | pass | See L3. |

## Findings
**High:** none.

**Medium**
- **M1:** crafted cursors (a numeric id, or a year near 1 or 9999) give 500 instead of 400 (`api/services/cursor.py`).
- **M2:** a revoked key still works through a live cookie session (`api/web_edge/auth.py`).
- **M3:** the per-IP sign-in limit sees the proxy IP when hosted, so all visitors may share one limit. This is hosting-only, so it's parked as Q12.

**Low**
- **L1:** sign-out doesn't clear the Ask history in localStorage.
- **L2:** `DELETE /v1/session` skips CSRF when a bearer header is also present.
- **L3:** the frontend CI workflow doesn't run on backend changes.
- **L4:** a session can be left behind if building the response fails after the session is created.

## Checked and fine
- **Session handling:**
  - There's no session fixation.
  - The session id is stored hashed.
  - The key is never stored or logged.
  - Logout deletes the session.
  - A disabled principal is cut off.
  - The bearer wins over the cookie.
- **Cookie and CSRF:** the cookie flags are right, and the CSRF comparison is constant time.
- **Preview:** preview strips `kb:write` and `admin`.
- **Gateway and data:**
  - Every product route goes through the gateway.
  - Migration 0006 is narrow.
  - All SQL is parameterised.
  - RLS holds, and responses carry no hash or secret.
- **Frontend:** the frontend never stores the key and sends the CSRF token.

## Architect disposition
- M1, M2 and L1–L4 go to the Builder, each with a test.
- M3 is parked under Q12 (hosting).
- Existing tests weren't weakened. `test_ui_proxy_config.py` was rewritten because the feature it tested was removed on purpose. The tests in it now check that the feature is gone.

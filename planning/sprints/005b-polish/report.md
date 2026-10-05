# Sprint 005b: Polish round. Report

The backend and frontend Builders returned their reports as text. The Architect saved this summary, re-ran every check and signed off the copy.

## 1. Acceptance
| Check | State | Evidence |
|---|---|---|
| A1 backend checks | done | Architect re-run: 875 passed, 0 skipped. ruff clean, mypy clean (89 files) |
| A2 overview, requests, reason codes | done | `api.txt`, plus the M1 and L1 tests |
| A3 lint, tsc, Vitest | done | Architect re-run: 162 passed |
| A4 Playwright (a)–(e) | done | Architect re-run: 70 passed |
| A5 axe, both themes | done | `axe.txt` (0 violations) |
| A6 Lighthouse | done | Desktop 99, mobile 85 (`lighthouse-*.json`) |
| A7 code splitting | done | `chunks.txt`. GSAP and WebGL only in landing chunks (Architect grep) |
| A8 copy | done | `copy-check.txt`, plus the Architect's line-by-line sign-off below |
| A9 tokens | done | `tokens.txt`. Brand blue removed |
| A10 docs | done | UI_GUIDELINES index, design skill, FRONTEND_STATE |
| A11 DTCG tokens and drift check | done | `tokens-build.txt` |
| A12 `docs/design/` and ADR-0010 | done | six docs plus ADR-0010 |
| A13 color guard | done | `color-guard.txt`, plus 32 ESLint probe tests |

## 2. What changed
- **API:**
  - `/v1/overview`, `/v1/requests` and `/v1/requests/{id}`, all audit:read.
  - `/v1/reason-codes`, from the catalogue in `gateway/reasons.py`.
  - The console's own reads are left out of the counts by default, unless they were denied. Pass `include_console_reads=true` to include them.
- **UI:**
  - Ink-and-paper tokens in DTCG JSON, built into CSS with Style Dictionary.
  - The new landing page and a How it works page.
  - An Overview as the console home.
  - Requests with a drawer.
  - Deny emphasis.
  - Plain reasons everywhere.
  - A governance line in Ask.
  - A guided walkthrough.
  - A session menu and a Cmd+K command palette.
  - Route-level lazy chunks.
  - A components polish pass.
- **Docs:** `docs/design/` (README, DESIGN_SYSTEM, CONTENT_STYLE, ACCESSIBILITY, COMPONENTS, PATTERNS), ADR-0010, and UI_GUIDELINES as an index.

## 3. Tests
- **Backend:** 805 tests before the sprint, **875 after**. 0 skipped.
- **Frontend:** 162 Vitest tests and 70 Playwright tests.

## 4. Copy sign-off (QA M3)
The Architect read every landing, story and How it works line against the may-claim list in `docs/design/CONTENT_STYLE.md`. Three changes were made at sign-off:
- **Model client:** "Agent code cannot reach the model client directly, and a test enforces it" became "Agent code does not import the model client, and a test checks it." The import guard checks direct imports only (see risk N2).
- **Story step title:** the last step was renamed from "Receipt" to "Record", and its heading now reads "from the question to the record". Receipts are a console view, and signed receipts are Sprint 008.
- **Writer guidance:** CONTENT_STYLE now asks "can I see what they did?" instead of "prove".

Every other line maps to a may-claim item and is accurate.

## 5. QA follow-ups
- **Fixed with tests:** M1, M2 and L1, L3–L8.
- **Fixed at sign-off:** M3.
- **Recorded as risk:** L2 is S5b-1 in RISKS.

## 6. Decisions
- **WebGL ring:** kept as a quiet background, because both Lighthouse targets are met.
- **`query_blocked` deny:** it's a 400 error, not a 403, so the UI maps it to a deny view.
- **`blocked_terms`:** the policies API doesn't return this field, so the UI never names it for `query_blocked` (Q15).
- **Storybook:** deferred (Q14).

## 7. Not verified here
- A human visual review of the screens.
- The UI image build.
- CI running on GitHub.

## 8. Commit blocks
These are in `planning/COMMIT_PLAN.md` under Sprint 005b.

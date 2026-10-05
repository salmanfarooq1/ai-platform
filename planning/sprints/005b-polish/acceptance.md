# Sprint 005b: Acceptance
| # | Check | Evidence |
|---|---|---|
| A1 | Backend: ruff, mypy, DDL guard and the full suite pass, with 0 skipped | `backend-*.txt` |
| A2 | Overview, requests and reason codes are tested: counts match seeded data, a deny anywhere makes the request a deny, the cursor works, a foreign request id gives 404, a missing scope gives 403 plus a deny row, RLS holds, and every emitted reason code has a catalogue entry | `api.txt` |
| A3 | Frontend: lint, `tsc` and Vitest pass. The Vitest tests cover the reason sentence, deny emphasis, the governance line, the overview tiles, the drawer and the command palette | `frontend-unit.txt` |
| A4 | Playwright passes against the real API. The cases are listed below. | `playwright.txt` |
| A5 | axe finds 0 serious or critical violations on the landing page, How it works, Overview, Requests with the drawer open, and the walkthrough, in both themes | `axe.txt` |
| A6 | Landing Lighthouse desktop is ≥ 90, and mobile is ≥ 75 or "not verified here" | `lighthouse-*.json` |
| A7 | Code splitting: each route is its own chunk, and a build grep shows no GSAP or WebGL in `/app` chunks | `chunks.txt` |
| A8 | Copy: the headline and subline are exact, there are no em-dashes, no banned words and no "demo", and every landing claim maps to the may-claim list | `copy-check.txt` |
| A9 | Tokens: the brand blue is gone (grep), and contrast ratios for all text pairs in both themes are listed | `tokens.txt` |
| A10 | Docs: UI_GUIDELINES, the design skill and FRONTEND_STATE are updated | diff |

## A4: Playwright cases
- **(a)** The walkthrough shows allowed and blocked side by side, with the blocked one at the guardrails stage.
- **(b)** Ask shows the governance line, and the line opens the request drawer.
- **(c)** Overview's blocked number opens the request list filtered to deny.
- **(d)** Cmd+K jumps to a request id.
- **(e)** A deny shows its plain sentence and the policy field.
| A11 | `ui/tokens/tokens.json` is valid DTCG. `tokens.css` is generated from it, and CI fails on drift | `tokens-build.txt` |
| A12 | `docs/design/` has README, DESIGN_SYSTEM, CONTENT_STYLE, ACCESSIBILITY, COMPONENTS and PATTERNS. UI_GUIDELINES is now an index. ADR-0010 is written | diff |
| A13 | A color literal outside the tokens file fails lint. The AA pairs test passes | `color-guard.txt` |

## Sign-off
Sprint 005b is accepted. The Architect re-ran the checks: 875 backend tests, 162 Vitest tests and 70 Playwright tests all passed. The copy was signed off line by line. See `report.md` and `qa-review.md`.

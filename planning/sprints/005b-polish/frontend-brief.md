# Sprint 005b: Frontend builder brief

You are the frontend Builder for Sprint 005b in `/home/user/ai-platform`. You work autonomously and fix your own problems. The backend contract is built (blueprint §1). Its routes are in `docs/openapi.json`, and `ui/src/api/schema.d.ts` is already regenerated.

## Read first
1. `AGENTS.md`.
2. `.claude/skills/governed-design/SKILL.md` and what it points to.
3. This folder: `requirements.md` (including "Standard design documentation"), `blueprint.md` §2-§4 and `acceptance.md` (A3-A13).
4. `planning/FRONTEND_STATE.md`: the current state, and the may-claim and must-not-claim lists.
5. The current `ui/`.

## Contract notes from the backend build
- **Console reads are left out by default.** `/v1/overview` and `/v1/requests` hide requests that are only console reads (`audit.read` or `analytics.read`). The parameter `include_console_reads=true` shows them. Add an "Include console views" toggle to the Requests page, off by default.
- **Reason catalogue.** `/v1/reason-codes` returns the catalogue. Fetch it once and cache it (TanStack Query, long `staleTime`). Use it everywhere a reason code appears.
  - The decision row's `stage` is the source of truth. The catalogue's `stage` is only a hint.
  - For `query_blocked`, don't say a policy key caused it unless the tenant has `blocked_terms`. The sentence already covers injection patterns.
- **Overview** counts requests. Each number links to `/app/requests` with the matching filter.

## Build
Everything in `requirements.md` items 1-17, the routes in blueprint §2, the walkthrough in §3, and the tokens in §4.

Order of work:
1. **Tokens first.** Create `ui/tokens/tokens.json` in DTCG format. Generate `tokens.css` with Style Dictionary v4 through the `npm run tokens` script. Remove the brand blue. Add the color-literal lint guard and the AA pair test.
2. **Components polish pass.** Unify radii, focus rings (seal color), hover, density and states.
3. **Shell.** Add the session menu, the Cmd+K palette (Radix Dialog plus a filtered list, or `cmdk` if it's MIT and small), and route-level lazy chunks.
4. **Overview, Requests with the drawer, deny emphasis, the governance line in Ask, and the walkthrough.**
5. **Landing page and `/how-it-works`.**
   - Use the exact headline and subline.
   - The hero is built from the real components with example data, labelled as examples.
   - Include the use-cases strip and the "why outside the agent" point. There is no problem section.
   - **WebGL:** keep the ring only as a quiet background if Lighthouse desktop stays at 90 or above and mobile at 75 or above. Otherwise remove it and say so.
6. **Design docs:**
   - Write `docs/design/` (README, DESIGN_SYSTEM, CONTENT_STYLE, ACCESSIBILITY, COMPONENTS, PATTERNS).
   - Turn `docs/UI_GUIDELINES.md` into an index that keeps its history.
   - Write ADR-0010 in `docs/adr/` in the existing ADR style, and add it to `docs/adr/README.md`.
   - Update the design skill so it points to `docs/design/`.
   - Update `planning/FRONTEND_STATE.md` so it matches what you built.
7. **CI:** add the token drift check to `.github/workflows/frontend.yml`.

## Tests
- Vitest covers the items in A3.
- Playwright covers A4 (a)-(e) against the real API (`scripts/e2e/serve.py`).
- Update the existing Playwright specs where routes or copy changed. Keep every assertion's intent; never weaken one.
- axe covers the A5 pages.
- Lighthouse runs on desktop and mobile with the Chromium at `/opt/pw-browsers`. If mobile can't run, mark it "not verified here".

## Run
If Postgres, Redis or dockerd is down, start it:
```
(dockerd > /tmp/dockerd.log 2>&1 &)
docker compose up -d postgres redis
```
In `ui/`, run `npm run tokens`, `npm run lint`, `npx tsc --noEmit`, `npm test -- --run`, `npm run build` and `npx playwright test`. Never run `playwright install`.

Save the evidence files that acceptance.md names to `planning/sprints/005b-polish/evidence/`.

## Rules
- Never weaken, skip or delete tests.
- No secrets.
- No commits or pushes.
- No "demo" wording.
- No em-dashes or banned words.
- Content stays within the may-claim list.
- Simple sentences in docs.
- Don't change backend code. If you think the contract needs a change, stop that item and report it.

## Return (text)
- The files changed.
- The numbers: lint, tsc, Vitest, Playwright, axe, Lighthouse desktop and mobile, and chunk sizes.
- Each of A3-A13: done, not done, or not verified here, with the evidence file.
- The WebGL decision and why.
- Deviations and open questions.

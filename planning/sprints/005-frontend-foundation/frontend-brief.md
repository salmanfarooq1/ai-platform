# Sprint 005: Frontend builder brief

You are the frontend Builder for Sprint 005 in `/home/user/ai-platform`. You work autonomously and fix your own problems. The backend slice is already built. Its routes are in `docs/openapi.json`, and the contract is in `blueprint.md`.

## Read first
1. `AGENTS.md`
2. `.claude/skills/governed-design/SKILL.md`, in full, then the parts it points to:
   - `.claude/skills/apple-design/SKILL.md` (motion and materials)
   - `references/taste/` (bans §9, landing rules)
   - `docs/UI_GUIDELINES.md`
3. This folder: `requirements.md`, `blueprint.md` (§4 and §5) and `acceptance.md` (A4-A12)
4. The wireframes, which the Architect describes here: an app shell with a grouped sidebar (Workspace, Governance, Platform), a top bar with the tenant crumb, a mode chip and a theme toggle.
   - **Decisions:** a filter chips row, then a table on the left and a detail panel on the right. The panel shows the verdict badge, a vertical stage trace and a receipt `dl` in mono.
   - **Ask:** a question box with Search and Agent modes and a KB chip, then the answer with a verdict and confidence, evidence cards, and an "Open receipt in Decisions" link.
   - **Policies:** a version list and a JSON document view.
   - **Keys:** a table of prefixes and scopes.
   - **Usage:** three stat tiles and a chart.
   - **Agent runs:** a runs table and a step timeline.
   - **Landing:** a hero, the scroll story "Agent asks → Gateway → Policy → Allow or Deny → Receipt", the capabilities, and a call to action.
5. The current UI in `ui/src`. Its API calls show the existing search, agent, documents, ingest, health and analytics endpoints.

## Build
1. **Migrate `ui/` to TypeScript (strict).**
   - Vite, React 18, React Router.
   - Tailwind wired to the CSS variables in `ui/src/styles/tokens.css`. Add the verdict tokens `--allow`, `--deny` and `--escalate` (each with a `-tint`, in light and dark, AA on surfaces).
   - shadcn/ui via its CLI. If the CLI can't reach its registry here, copy the component sources from the `shadcn` npm package or write them from the Radix primitives, with the source noted in a comment.
   - Phosphor icons, Geist fonts from the `geist` npm package, and TanStack Query.
2. **API client:** `npm run gen:api` (openapi-typescript) to `src/api/schema.d.ts`, plus a typed client per blueprint §4.
3. **Screens and routes** per blueprint §4. Every screen has loading (skeleton), empty and error states. The error state shows `code` and `request_id`.
4. **Landing page:**
   - GSAP with ScrollTrigger (npm `gsap`; all plugins are free) for the pinned scroll story and text reveals.
   - The hero is three.js through `@react-three/fiber` and `@react-three/drei` (MIT). It's lazy-loaded after first paint with a poster fallback.
   - Reduced motion shows the end states and the poster.
   - 21st.dev and threeui.com are blocked in this container (Q11), so build equivalents and note the sources in comments.
   - Use real copy, no fake screenshots, no em-dashes, and none of the banned words.
5. **Tests:**
   - Vitest + Testing Library for the components in A5.
   - Playwright in `ui/e2e/`. `webServer` runs `poetry run python scripts/e2e/serve.py` and `vite preview` with the proxy. Cover the A6 allow and deny cases, A7 reduced motion and chunk checks, and A9 axe in both themes.
   - Lighthouse: try `npx lighthouse` with the Chromium at `/opt/pw-browsers`. If it can't run, write `scripts/verify/lighthouse.sh` and mark A8 "not verified here".
6. **Parity, then removal (A10).**
   - Once Ask, Library and System work, delete the old `.jsx` files and the nginx preview-key injection (`ui/docker-require-preview-key.sh` and the template line).
   - Update `ui/Dockerfile.ui` for the TypeScript build.
   - Image builds are blocked here, so mark that "not verified here".
7. **CI:** add the frontend jobs to `.github/workflows/` (lint, tsc, vitest, build, and Playwright with Postgres and Redis services).
8. **Docs:**
   - Refresh `docs/UI_GUIDELINES.md` through the design skill: verdict states, trace pattern, console versus workspace, themes, AA, and states. Keep its history sections where they're still true.
   - Update the README's Getting Started for the UI.

## Run
If Postgres, Redis or dockerd is down, start it:
```
(dockerd > /tmp/dockerd.log 2>&1 &)
docker compose up -d postgres redis
```
In `ui/`, run `npm ci`, `npm run lint`, `npx tsc --noEmit`, `npm test -- --run`, `npm run build` and `npx playwright test` (Chromium at `/opt/pw-browsers`; don't run `playwright install`). Save the evidence files that A4-A12 name.

## Rules
- Never weaken, skip or delete tests.
- No secrets in code.
- No commits or pushes.
- No "demo" wording.
- No brand name for the platform.
- Simple sentences in docs.
- Don't change backend code, except a minimal fix you clearly report. The contract is fixed.

## Return (text)
- The files changed.
- The numbers: lint, tsc, vitest, Playwright, Lighthouse score, axe.
- Every A4-A12 check, with done, not done, uncertain or not verified here, and the evidence.
- Deviations, decisions and open questions.

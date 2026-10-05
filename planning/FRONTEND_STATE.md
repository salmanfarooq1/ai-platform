# Frontend: current state

This is a snapshot for design and content work. It is checked against the code in `ui/` as of Sprint 009. It says plainly what is built, what is a placeholder and what has not been reviewed.

The design rules live in `docs/design/` (index: `docs/UI_GUIDELINES.md`). The may-claim and must-not-claim lists moved to `docs/design/CONTENT_STYLE.md`.

## 1. The product in one paragraph
The Governed Agent Platform sits between AI agents (or people) and the things they use: models, tools and document collections called knowledge bases. Every call goes through one gateway. The gateway checks:
- who is calling, and which tenant they belong to
- the tenant's policy
- the input guardrails
- the rate limit and the token budget

The answer is allow or deny, with a reason. Every call leaves a decision record: id, policy version, action, resource, verdict and the SHA-256 of the input. The input text itself is not stored. Tenants are isolated inside Postgres. If a check can't run, the call is denied.

**Audience, in order:** the person accountable for the agents (team lead, owner, risk owner), then the engineers who run them.

## 2. What exists in the UI today
The stack is React and TypeScript, with Tailwind and hand-built components on Radix (shadcn patterns), Geist and Geist Mono fonts, light and dark modes. GSAP and three.js load on the landing page only. Every route is a lazy chunk.

| Area | Route | State |
|---|---|---|
| Landing page (public) | `/` | Built. Headline "Your agents can only ever do less." and the subline. The hero is the real Receipt and deny components with example data, labelled as examples. A use-cases strip, one "why outside the agent" point, the scroll story of one request, eight capability lines, a call to action. A quiet WebGL ring sits behind the hero. |
| How it works | `/how-it-works` | Built. The checks in order, the policy, what a deny shows, the decision record, tenants and limits. Static, no GSAP or WebGL. |
| Sign in | `/signin` | Built. API key field. A read-only preview button appears when the host enables preview. A new browser opens the walkthrough first, then the Overview. |
| Overview | `/app` | Built. Checked, blocked, deny rate and budget used, each linking to `/app/requests` with its filter. Top deny reasons with plain titles. Requests per day. |
| Walkthrough | `/app/walkthrough` | Built. Runs one allowed and one blocked request (the input guardrails stop it) against the real API and shows both side by side, with stage trace, plain reason and a link to the request. |
| Requests | `/app/requests`, `/app/requests/:requestId` | Built. One row per request. Filters for outcome, action, policy version and time. An "Include console views" switch, off by default. A slide-over drawer with the verdict, deny emphasis, stage trace and receipt links. |
| Ask | `/app/ask` | Built. Search or Agent mode, a knowledge-base field, the answer with evidence and confidence, a verdict badge, the governance line ("Checked by policy v3 · 2 checks · allowed") that opens the drawer, "Open receipt in Decisions", and feedback buttons. A denied request shows the deny emphasis. |
| Library | `/app/library` | Built. Documents per knowledge base, plus upload. Upload answers at once with "Queued". Each row shows the status of its latest ingestion job (Queued, Processing, Ready or Failed with its error code), polled while a job is open (Sprint 007). |
| History | `/app/history` | Built. This browser's past questions only, stored locally and cleared on sign-out. |
| Decisions | `/app/decisions`, `/app/decisions/:id` | Built. One row per decision, with a detail panel: verdict, deny emphasis, stage trace and receipt. Links to its request. |
| Policies | `/app/policies` | Built, read-only. Version list and the policy document. Editing stays in the admin command line tool. |
| Keys and principals | `/app/keys` | Built, read-only. Key prefixes, scopes and dates. Secrets are never shown. |
| Usage | `/app/usage` | Built. Totals, by principal, by day (chart), and denials by cause. |
| Agent runs | `/app/runs` | Built. Each run shows its execution id and its status, read from the durable job queue (Sprint 007). A caller sees only runs in knowledge bases its policy allows, and without `audit:read` only its own runs. **Sprint 009:** a run that executed in a sandbox shows its steps as one rail: the gateway decisions and the sandbox's own events (started, exited, network call blocked, file access blocked, limit reached, log) in time order, each kind with its own icon and word. A blocked network call or file access is a deny state (red bar, "Denied", what was tried). A summary line says what the sandbox blocked. A run without sandbox events keeps the request trace. |
| Trust | `/app/trust` | Built (Sprint 008). Verify a receipt by decision id or by pasting one: valid or invalid, each check, chain position and key id. The decision panel has a "Verify receipt" link that opens it with the id. Retention settings (read only), the eval gate latest run and history, and a Grafana link when `GRAFANA_URL` is set. Needs `audit:read`. |
| System | `/app/system` | Built. Health of the API, the database and the cache. |

**Shell.** A grouped sidebar, a top bar with the tenant crumb, a mode chip, a Cmd or Ctrl plus K command palette (go to a screen, find a request id), a theme toggle and a session menu (who you are, tenant, scopes, theme, sign out).

## 3. Design rules in force
The sources are `docs/design/` and the design skill `.claude/skills/governed-design/SKILL.md`. ADR-0010 records the palette decision.

**Ink and paper.** Warm paper neutrals and near-black ink. Primary buttons are ink. One rare seal color (deep petrol) marks the logo dot, links, focus rings and a few landing highlights. Verdict colors are the only strong color. The old brand blue is gone.

| Role | Light | Dark |
|---|---|---|
| Page | `#F6F4EF` | `#131312` |
| Surface | `#FDFCFA` | `#1C1B19` |
| Ink and text | `#18181B` | `#ECEAE4` |
| Seal | `#0B5D6E` | `#5DB7C4` |
| Allow | `#146B41` | `#4CD38A` |
| Deny | `#BF2A22` | `#FF7A72` |
| Escalate | `#8F5600` | `#F2B04A` |

**Tokens are data.** `ui/tokens/tokens.json` (W3C Design Tokens format) is the source. `npm run tokens` generates `ui/src/styles/tokens.css` with Style Dictionary v4. CI fails on drift. ESLint fails on color literals outside the generated file. A test checks every contrast pair in `docs/design/ACCESSIBILITY.md` in both themes.

**Surfaces.** Console: dense, quiet, exact. Workspace: calm. Landing page: editorial, with the headline as the only loud element.

**Verdicts** always use an icon, a word and a color together. **Deny is the loudest state:** the failing stage in red, one plain sentence from the reason catalogue, the policy field and the policy version.

**States.** Every screen has loading (skeletons), empty and error states. Errors show the error code and the request id.

**Motion.** In the app, only motion that explains a change, at 100 to 250 ms. On the landing page, a GSAP scroll story and a quiet WebGL ring that loads after first paint. With reduced motion: no GSAP, no WebGL, a static poster.

Browser storage: the allowed `localStorage` keys are `theme`, `density`, `walkthrough-seen`, `ask-history` and `collection` (a knowledge-base slug, not a secret). The list is in `docs/design/PATTERNS.md`.

## 4. What's measured (and how)
Evidence files are in `planning/sprints/005b-polish/evidence/`.
- **Unit tests (Sprint 009):** Vitest and Testing Library, 207 tests (the new ones cover `RunSteps`, the sandbox words and the runs page with and without sandbox events), all passing. They cover the reason sentence, deny emphasis, the governance line, the overview tiles, the drawer, the command palette, the walkthrough, the session menu, the tokens and the contrast pairs. ESLint and `tsc --noEmit` are clean.
- **Playwright (Sprint 009):** 82 tests against the real API (fakes for the model and embeddings), all passing. The sandbox spec reads two runs that were made while seeding with a fake sandbox, so it proves the page and the runs API, not OpenShell. They cover the walkthrough, the governance line and drawer, Overview to the deny-filtered list, the palette, a deny's sentence and policy field, the first-run rule, console views, the session menu, landing, reduced motion, preview, and phone widths.
- **Accessibility:** axe found 0 violations of any impact on 12 pages and states in each theme (landing, How it works, Overview, Requests list, the drawer, the walkthrough, the palette, the session menu, Ask with an answer, Ask denied, Decisions allowed and denied).
- **Landing page performance:** Lighthouse 12, run in the build container against `vite preview`. Desktop 99. Mobile 85 (simulated throttling). The ring loads after the load event, so Lighthouse sees little of its cost.
- **Code splitting:** every route is its own chunk. A grep finds no GSAP or WebGL in any chunk that loads under `/app`.
- **Copy:** `npm run copy-check` confirms the headline and subline, no long dashes, no banned words, and that each landing claim maps to the may-claim list.

## 5. Honest gaps (architect's view)
- **No human has looked at the screens.** Tests prove that it works, that it is accessible, and that it never shows secrets. They say nothing about whether it looks good, reads well or feels premium. The builder looked at four screenshots (landing, walkthrough, drawer, Overview) and fixed what was plainly wrong. A real visual review is still the most important next step.
- **The palette values are a builder's call.** They start from the blueprint values. All text pairs pass AA, but the seal may prove too quiet and the paper too warm.
- **The components are hand-built.** 21st.dev, ThreeUI and the shadcn registry were blocked in the build container, so no component was copied from those sites.
- **The tenant policy view does not carry `blocked_terms`.** `/v1/policies` returns a document view without that key. So for `query_blocked` the UI never names a policy field. It would name `blocked_terms` if the API returned it.
- **The walkthrough's normal question can find nothing.** It asks "What topics do these documents cover?" and a knowledge base whose passages share no words with it can answer 404. The walkthrough then says the gateway allowed the call and no passage matched, and still shows the allow decision.
- **Escalate (needs approval) is designed but not built.** No approval workflow exists in the backend yet. Content must not promise approvals.
- **Trust page:** verification marks only signed fields as verified. Other fields are shown as context.
- **A worker must run.** Uploads and agent runs stay Queued until a worker process picks them up (`python -m workers` or `EMBEDDED_WORKERS=1`).
- **No brand name or visual identity beyond the tokens.** The descriptive name is settled. A named identity is still open.
- **Storybook is not used.** `docs/design/COMPONENTS.md` and the Vitest tests do that job (Q14).

## 6. What content may claim and must not claim
These lists moved to `docs/design/CONTENT_STYLE.md`. Read them there. A new claim on a public page needs an item on the may-claim list first.

## 7. Open design questions
1. Should the platform get a name and identity, or stay descriptive? (Descriptive for now.)
2. Does the seal color need more presence once a human has looked at the screens?
3. Should the WebGL ring stay? It stays while Lighthouse holds desktop 90 and mobile 75. It is removed if either falls under.
4. When approvals are built, how loud should the escalate state be?

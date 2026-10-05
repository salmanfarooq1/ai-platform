# UI guidelines

> Version 2.0.0, October 2026
> The reference for the web UI in `ui/`.
> Built on the project design skill (`.claude/skills/governed-design/SKILL.md`), which merges the `apple-design` skill, the taste skill and this file. When they disagree, accessibility and honesty come first, then this file, then the skill. Section numbers in brackets, like [§12], point to the `apple-design` skill.

---

## Overview

The platform runs governed agents on business data. The UI has two jobs. It lets people ask questions and read answers with their evidence. It lets engineers and risk owners see what the platform allowed or denied, under which policy.

**Three rules that do not bend:**

1. **Every answer shows its evidence.** Citations, confidence and the verdict sit next to the answer.
2. **Every call leaves a receipt.** The UI can open the decision behind any answer. It never shows the input text, because the platform does not store it.
3. **Nothing waits for no reason.** Feedback starts on press. Motion is interruptible. No artificial delays.

---

## 1. Stack and files

| Part | Choice |
|---|---|
| Build | Vite, React 18, React Router 6, TypeScript in strict mode |
| Styling | Tailwind, mapped to the CSS variables in `ui/src/styles/tokens.css` |
| Components | shadcn/ui patterns on Radix primitives, in `ui/src/components/ui` |
| Data | TanStack Query. Types come from `docs/openapi.json` through `npm run gen:api` |
| Icons | Phosphor (`@phosphor-icons/react`), regular weight in the app, light on the landing page |
| Fonts | Geist Sans and Geist Mono from the `geist` npm package, self-hosted |
| Landing only | GSAP with ScrollTrigger and SplitText, three.js through `@react-three/fiber` and `@react-three/drei` |

Layout of `ui/src`: `app` (router, providers, shell, session, theme), `api` (client, endpoints, generated schema), `features/<area>` (screens), `components/ui` (base components), `components/governance` (verdict badge, trace, receipt, states), `landing` (its own lazy chunk).

The shadcn registry is not reachable from every build machine. The components in `components/ui` are written from the shadcn patterns on Radix, and each file names its source in a comment. Never hard-code a hex color in a component. Use a token.

---

## 2. Console and workspace

The app has two characters. They share tokens and components. They differ in density and tone.

| Surface | Screens | Density | Character |
|---|---|---|---|
| Workspace | Ask, Library, History | Calm. 12px radius cards, generous spacing | The answer and its evidence are the loudest thing on the page |
| Console | Decisions, Policies, Keys, Usage, Agent runs | Dense. Compact rows (32px), mono for ids | Exact, quiet, scannable. Tables, filters, timelines |
| Trust and System | Trust, System | Plain and factual | Numbers and states, no decoration |
| Landing | `/` | Editorial, large type, one scroll story | The only place with scroll-driven motion and WebGL |

Console tables have a density switch: compact (32px rows) by default, comfortable (40px). Numbers are right-aligned in tabular figures. The console has no scroll-triggered entry animation.

---

## 3. Color and themes

Color carries meaning. It is never the only signal: every state also has a word or an icon.

### Brand and neutrals

| Token | Light | Dark | Role |
|---|---|---|---|
| `--brand` | `#2F5BEA` | `#6E8BFF` | Primary action, focus ring, links, selected state |
| `--brand-tint` | `rgba(47,91,234,0.10)` | `rgba(110,139,255,0.16)` | Selected rows and active nav |
| `--ink` | `#0B0D12` | `#F3F4F6` | Logo container, strongest text |
| `--bg-canvas` | `#F6F6F4` | `#0E0F12` | Page background. Never pure white or pure black |
| `--bg-surface` | `#FFFFFF` | `#16181D` | Cards, panels, dialogs |
| `--bg-muted` | `#F0F0EE` | `#1C1F25` | Inputs, code blocks, table headers |
| `--material-thin` | `rgba(255,255,255,0.62)` | `rgba(22,24,29,0.62)` | Sidebar and top bar |
| `--hairline` | `rgba(0,0,0,0.07)` | `rgba(255,255,255,0.08)` | Every border and divider |
| `--text-primary` | `#0B0D12` | `#F3F4F6` | Body and headings |
| `--text-secondary` | `#565B66` | `#A3A8B3` | Supporting copy |
| `--text-tertiary` | `#5F646F` | `#8E94A0` | Labels, metadata, timestamps |

### Semantic and verdict tokens

Each has a text color and a `-tint` for its background. The contrast column is the text color on `--bg-surface`, and on its own tint laid over the surface. All pass WCAG AA (4.5:1) for normal text.

| Token | Light | Dark | Contrast light (surface / tint) | Contrast dark (surface / tint) |
|---|---|---|---|---|
| `--allow` | `#146B41` | `#4CD38A` | 6.5 / 5.6 | 9.3 / 7.1 |
| `--deny` | `#BF2A22` | `#FF7A72` | 5.9 / 5.0 | 7.0 / 5.6 |
| `--escalate` | `#8F5600` | `#F2B04A` | 6.0 / 5.2 | 9.4 / 7.2 |
| `--success`, `--warning`, `--danger` | same as allow, escalate, deny | same | same | same |

### Themes

- The default follows `prefers-color-scheme`. The theme toggle in the top bar sets `data-theme="light"` or `data-theme="dark"` on `<html>` and saves the choice in `localStorage`. A small script in `index.html` applies it before first paint.
- Tokens are defined three times in `tokens.css`: `:root` (light), `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, and `[data-theme="dark"]`.
- Theme changes ease over 200ms.
- Every screen is checked in both themes with axe (see section 12).

### Confidence scale

| Range | Label | Color |
|---|---|---|
| 0.75 to 1.00 | HIGH | `--success` |
| 0.50 to 0.74 | MEDIUM | `--warning` |
| below 0.50 | LOW | `--danger` |

The tint is always painted over `--bg-surface`, not over whatever is behind the element. This keeps contrast the same in selected rows and on tinted panels.

---

## 4. Typography

Geist Sans for the UI. Geist Mono for ids, hashes, codes and JSON. Inter and JetBrains Mono are retired.

| Token | Size | Weight | Leading | Tracking | Use |
|---|---|---|---|---|---|
| `display` | `clamp(2.25rem, 4vw, 3.25rem)` | 600 | 1.05 | `-0.025em` | Landing headline |
| `title-1` | `1.75rem` | 650 | 1.15 | `-0.02em` | Page titles, stat values |
| `title-2` | `1.25rem` | 600 | 1.25 | `-0.012em` | Section titles |
| `headline` | `1rem` | 600 | 1.35 | `-0.006em` | Card titles |
| `body` | `0.9375rem` | 400 | 1.55 | `0` | Answers and prose |
| `callout` | `0.875rem` | 400 | 1.45 | `0` | Supporting copy, controls |
| `footnote` | `0.8125rem` | 500 | 1.4 | `0.005em` | Metadata, table cells |
| `caption` | `0.6875rem` | 600 | 1.3 | `0.06em` | Uppercase labels |

- Sentence case for buttons, nav and titles. Uppercase only for `caption`.
- Sizes are in `rem`. Tailwind exposes them as `text-body`, `text-callout`, and so on.
- Numbers in tables and stats use tabular figures (`.tabular`).
- Emphasis uses weight, not size or color.

---

## 5. Information architecture

| Group | Item | Route | Contains |
|---|---|---|---|
| Public | Landing | `/` | What the platform does, the scroll story, the call to action |
| Public | Sign in | `/signin` | API key form. In public-preview mode also "Continue in read-only preview" |
| Workspace | Ask | `/app/ask` | Question box with Search and Agent modes and a knowledge base field. Answer, verdict, confidence, evidence, receipt link |
| Workspace | Library | `/app/library` | Documents table and the upload dialog |
| Workspace | History | `/app/history` | This browser's asks, each linking to its trace |
| Governance | Decisions | `/app/decisions`, `/app/decisions/:id` | Filter chips, table, detail panel |
| Governance | Policies | `/app/policies` | Version list and the JSON document |
| Governance | Keys | `/app/keys` | Principals, key prefixes and scopes |
| Governance | Usage | `/app/usage` | Three stat tiles, a chart, denials by stage |
| Governance | Agent runs | `/app/runs` | Runs table and a step timeline |
| Platform | Trust | `/app/trust` | A placeholder until the trust sprint |
| Platform | System | `/app/system` | Service health, mode, limits |

- `/app/*` without a session redirects to `/signin` and returns the person to the page they asked for.
- The shell has a grouped sidebar (Workspace, Governance, Platform), a top bar with the tenant crumb, a mode chip and a theme toggle, and a skip link. Below 768px the sidebar becomes a menu in the top bar.
- Agent runs are built from decisions with the action `agent.run`, grouped by request id, until the platform has a runs API.
- History is stored in `localStorage` only. It holds the question text for this browser, and nothing is sent anywhere.

---

## 6. Governance patterns

These patterns are our own. They always apply.

### Verdict states

Each verdict has a token pair, an icon and a word.

| Verdict | Token | Icon | Word |
|---|---|---|---|
| Allow | `--allow` | check circle | Allowed |
| Deny | `--deny` | prohibit | Denied, plus the reason code in mono |
| Escalate | `--escalate` | hand | Needs approval |
| Not recorded | `--warning` | warning circle | Not recorded |

Component: `VerdictBadge` in `components/governance`. It carries `data-verdict` for tests.

### Trace timeline

A vertical rail of the gateway decisions in one request, oldest first. Each step shows the action and resource in mono, its verdict, the stage, a timestamp in mono and the time to the next step. The denied step is the visual anchor: a left bar in `--deny`. The step that is open is marked with `aria-current="step"`. Steps never open in a modal.

Component: `TraceTimeline`.

### Receipt

A definition list in mono: decision id, request id, policy version, tenant, principal, action, resource, stage, reason, input SHA-256 and time. Each value has a copy button. A missing value reads "none". The raw input is never shown.

Component: `Receipt`.

### Secrets

The Keys screen shows the prefix, scopes, created time and last-used time. A last-used time that the platform does not track reads "not tracked". A secret appears once, when a key is created, in a copy-once dialog, and is never fetched again. Editing keys and policies is not in the UI. The admin CLI is the writer.

---

## 7. States

Every screen has a loading, an empty and an error state.

- **Loading:** skeletons in the final layout shape. Never a centered spinner on a table.
- **Empty:** say what would appear here and how to make it appear. Example: "No decisions yet. Every model, tool and knowledge base call writes one row here."
- **Error:** show the API error `code` and `request_id` in mono, a plain message, and a "Try again" button. Components: `ErrorState`, `EmptyState`, `TableSkeleton`.
- **Denied:** a denial is not an error. It has its own panel with the verdict badge, the reason code and a link to the receipt.
- **Read-only session:** actions the session cannot do are disabled, and the page says why.

---

## 8. Components

- Buttons: primary is `--brand` fill. Secondary is a bordered surface. Ghost is text only. Press feedback is `scale(0.97)` on pointer-down. One primary button per view.
- Inputs: `--bg-muted` fill, hairline border, 36px height, a 2px `--brand` focus ring with offset. Invalid inputs set `aria-invalid` and show the message below.
- Segmented control: Radix toggle group. Used for the Ask mode, the verdict filter and the row density.
- Cards: `--bg-surface`, hairline border, 12px radius in the workspace and 8px in the console. No cards inside cards.
- Tables: real `<table>` with a caption, `scope="col"` headers, a muted header row and hairline dividers. Rows are links for keyboard use. Numbers are right-aligned.
- Dialog: Radix dialog. Focus is trapped, `Esc` closes, focus returns to the trigger.
- Stat tile: `caption` label, `title-1` value in tabular figures.
- Chart: one brand series, hairline gridlines, axis labels in `caption`, and a hidden table with the same numbers.
- Radius: 8px console, 12px workspace, up to 24px on the landing page only.
- Shadows are near flat in the app (opacity below 0.06). Hairlines do the structure.

---

## 9. Motion

- **In the app:** only motion that explains a change, such as a row expanding, a panel sliding or a timeline revealing. 150 to 250ms. Animate `transform` and `opacity` only.
- **Interruptible:** an animation can be redirected from its current value. Input is never blocked during a transition [§3].
- **Landing page:** GSAP with ScrollTrigger and SplitText runs the pinned scroll story ("Agent asks, Gateway, Policy, Allow or deny, Receipt") and the heading reveals. The story shows five panels that use the real console components with an example request, labelled as an example.
- **WebGL:** one three.js hero on the whole site, none in the app. A static poster is always in the page. The scene loads as its own chunk a few seconds after the page load and an idle moment, only when motion is allowed and WebGL works. It pauses when it is off screen.
- **Reduced motion:** GSAP is not loaded. The story is a plain list showing every step. The WebGL chunk is not requested and the poster stays. Springs become short fades.
- **Narrow screens:** below 768px the story is the plain list too, because the pinned layout does not fit.
- **Performance:** the landing page scores 85 or more in Lighthouse on desktop. Check it with `scripts/verify/lighthouse.sh`.

---

## 10. Voice and copy

- Short, plain sentences. Technical detail lives in the console, not on the workspace surface.
- Labels name the thing: "Add documents", not "Submit".
- Status copy says what is happening now.
- Errors say what happened and what to do next.
- Empty states invite the next step.
- Low confidence answers say so and tell the person to check the sources.
- No em-dash or en-dash in visible copy. Use a hyphen, a period or a colon.
- No filler words such as "elevate", "seamless", "unleash" or "next-gen". No invented numbers.
- The hosted mode is called `public-preview`. The platform has no brand name. Use functional names.

---

## 11. Iconography, depth and ambient background

- Phosphor icons only, regular weight in the app, light on the landing page. No emoji. Sizes: nav 18px, buttons 16px, inline 14px.
- The sidebar and top bar use `--material-thin` with a 24px blur. Cards and dialogs are solid. A translucent layer never sits on another translucent layer.
- `prefers-reduced-transparency` and `prefers-contrast: more` make materials solid.
- The canvas can carry a quiet top wash from `--ambient-wash`. Nothing moves in it.

---

## 12. Accessibility

- WCAG AA in both themes. Body text 4.5:1, large text 3:1.
- Every control works with the keyboard and has a visible focus ring. The shell has a skip link.
- Landmarks: `header`, `nav`, `main`, `aside` with labels. One `h1` per page.
- Live regions: the answer region is polite. Errors use `role="alert"`.
- Respect `prefers-reduced-motion`, `prefers-reduced-transparency` and `prefers-contrast`.
- axe runs in Playwright (`ui/e2e/a11y.spec.ts`) on the landing page, Ask (answer and denial) and Decisions (allow and deny detail), in both themes. The bar is zero serious or critical violations.

---

## 13. Pre-flight for any UI change

- [ ] Both themes are checked, and text passes AA.
- [ ] It works with the keyboard, focus is visible, and Radix primitives keep their ARIA.
- [ ] It works with reduced motion.
- [ ] Loading, empty and error states exist.
- [ ] No hard-coded colors, no em-dashes and no banned words.
- [ ] A verdict uses an icon, a word and a color together.
- [ ] Vitest and Testing Library cover the components, and Playwright covers the flow.

---

## 14. History

These parts of version 1 are still true and were kept: calm confidence as the goal, the neutral and brand tokens, the confidence scale, the type scale and casing rules, materials and depth, the motion rules (feedback on press, interruptible, transform and opacity only), and the accessibility rules.

What changed in version 2:

| Version 1 | Version 2 |
|---|---|
| Four destinations: Ask, Library, Insights, System | Three groups with eleven screens, plus the landing page and sign-in |
| Preview key added by nginx | A session cookie from `POST /v1/session`. No key in the browser or the proxy |
| CSS modules | Tailwind on the token variables, with shadcn/ui patterns |
| Inter and JetBrains Mono | Geist Sans and Geist Mono |
| Lucide icons | Phosphor icons |
| One collection picker in the top bar | A knowledge base field on Ask and Library. The field accepts any slug, so a person can see a denial |
| Plain JavaScript | TypeScript in strict mode, with a client generated from the OpenAPI file |

The old logo and mode badge rules still hold. The logo is a rounded square with three lines, the last one shorter and ending in a dot in `--brand`. The mode chip in the top bar shows `public-preview`, `local` or `prod`, and adds "read-only" for a preview session.

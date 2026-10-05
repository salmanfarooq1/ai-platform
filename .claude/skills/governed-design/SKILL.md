---
name: governed-design
description: The project design skill for the Governed Agent Platform UI (ui/). Every frontend builder reads and follows it before writing UI code: the console, the workspace, the trust pages and the showcase landing page. It is the agent-facing entry point. The source of truth is docs/design/. It merges the apple-design skill and the taste skill (main, soft and minimalist variants) with those docs, and says which rule wins when they disagree.
---

# Governed design

This skill is the single entry point for UI work in `ui/`. Read it in full, then read the parts of the sources it points to.

## The design docs are the source
The rules live in `docs/design/`. This skill summarizes them for agents and adds dials and motion practice. When this file and a design doc disagree, the doc wins.

| Read | For |
|---|---|
| `docs/design/README.md` | What each doc covers, owners, precedence |
| `docs/design/DESIGN_SYSTEM.md` | Identity, the seal color, color roles, type, spacing, radius, elevation, motion, surfaces |
| `docs/design/CONTENT_STYLE.md` | Voice, glossary, reason sentences, may-claim and must-not-claim lists, banned words |
| `docs/design/ACCESSIBILITY.md` | WCAG 2.2 AA, tests, the contrast pair table, known exceptions |
| `docs/design/COMPONENTS.md` | Every shared component. Add a row for each new one |
| `docs/design/PATTERNS.md` | Verdict, trace, receipt, deny emphasis, governance line, drawer, states |
| `docs/adr/0010-design-tokens-and-ink-paper-palette.md` | Why ink and paper, and why tokens are data |
| `docs/UI_GUIDELINES.md` | An index to the docs above, with the history |

Tokens are data: edit `ui/tokens/tokens.json`, run `npm run tokens` in `ui/`, and commit the generated `ui/src/styles/tokens.css`. CI fails on drift.

## Sources and precedence
When rules conflict, the higher item wins.
1. **Accessibility and honesty.** WCAG AA, keyboard use, `prefers-reduced-motion`, no fake data shown as real.
2. **`docs/design/`.** The product's tokens, components, patterns, states and copy rules. `docs/UI_GUIDELINES.md` is the index.
3. **This file.** Dials, surfaces and the governance patterns below.
4. **`.claude/skills/apple-design/SKILL.md`.** Motion physics, materials, feedback and restraint.
5. **`references/taste/`** (MIT, vendored unchanged):
   - `design-taste-frontend.md` for the landing page.
   - `minimalist.md` for the workspace and console.
   - `soft.md` for the landing page only, and only the parts listed below.

The taste skill says it is "not for dashboards". So the console takes only its anti-slop bans (section 9) and its accessibility and performance rules (section 6). It does not take its layout or motion rules.

## Design read
Reading this as: a governance product for engineers and risk owners, with a calm, premium, trust-first language. It leans toward Tailwind and shadcn/ui (Radix), themed from our tokens, with restrained motion.

## Surfaces and dials
Dials as defined in `design-taste-frontend.md` §1 (variance / motion / density, 1-10).

| Surface | Variance | Motion | Density | Character |
|---|---|---|---|---|
| Governance console (Decisions, Policies, Keys, Budgets, Agent runs) | 3 | 2 | 7 | Data-dense, quiet, exact. Tables, filters, timelines. |
| Workspace (Ask, Library, History) | 4 | 3 | 4 | Calm. The answer and its evidence are the loudest thing. |
| Trust and System | 3 | 2 | 5 | Plain and factual. |
| Showcase landing (public) | 7 | 6 | 3 | Premium, editorial, scroll story. |

## Governance patterns (our own; these always apply)
The full spec is `docs/design/PATTERNS.md`. In short:
- **Verdict states.** Each one has a token pair (text plus tint), an icon and a word. Never use color alone.
  - **Allow:** `--allow`, check icon, "Allowed".
  - **Deny:** `--deny`, block icon, "Denied", plus the reason code in mono.
  - **Escalate:** `--escalate`, hand icon, "Needs approval".
  - **Unrecorded / unavailable:** `--warning`, "Not recorded".
- **Trace / timeline.** A vertical rail of steps: actor → gateway stage(s) → verdict → receipt (decision id, policy version, input hash). Each step shows a timestamp in mono and its duration. The deny step is the visual anchor of a denied trace. Steps expand inline, not in a modal.
- **Receipt.** Decision id, policy version, tenant, principal, action, resource and the SHA-256 input hash. All monospace, each value copyable. The raw input text is never shown, because the platform does not store it.
- **Secrets.** Key screens show the prefix, scopes, created and last-used times only. The one-time secret appears once, in a copy-once dialog, and is never fetched again.
- **Deny emphasis.** A deny names the failing stage in red, gives one plain sentence from the reason catalogue (`/v1/reason-codes`), and shows the policy field and policy version behind it. The stage on the decision row is the source of truth. Use `DenyCallout`.
- **Governance line.** Under each answer in Ask: "Checked by policy v3 · 2 checks · allowed", linking to the request drawer.
- **Empty, loading and error states** exist for every screen.
  - Loading uses skeletons in the final layout shape, never a centered spinner on a console table.
  - Errors show the API error `code` and `request_id`, with a retry action.
  - Empty states say what would appear there and how to make it appear.
- **Density switch.** Console tables have compact rows (32px) by default and a comfortable option (40px). Numbers are right-aligned in tabular figures.

## Tokens
- **Source of truth:** `ui/tokens/tokens.json` (W3C Design Tokens format). `ui/src/styles/tokens.css` is generated from it by Style Dictionary (`npm run tokens`). Never edit the CSS by hand. Tailwind reads the CSS variables, and shadcn components use the same variables.
- **Ink and paper (ADR-0010):** warm paper neutrals, near-black ink, and verdict colors as the only strong color. Primary buttons are ink. The brand blue is removed.
- **One seal color** (deep petrol): the logo dot, links, focus rings and rare landing highlights. Never a button fill, a verdict or a chart color. No second accent.
- **Verdict tokens:** `--allow`, `--deny` and `--escalate`, each with a `-tint`, for light and dark. They pass AA for text on `--bg-surface`. The contrast pairs are listed in `docs/design/ACCESSIBILITY.md`, and a test checks them.
- **No color literals** in `ui/src`. ESLint fails on hex, rgb and hsl literals outside the generated file. A test guards the stylesheets.
- **Typography:**
  - Geist Sans for UI and Geist Mono for ids, hashes, reason codes and policy keys, self-hosted from the `geist` npm package (OFL).
  - Inter is retired. Tabular numbers in tables.
- **Radius:** 8px for console cards and inputs, 12px for workspace cards, and up to 24px only on the landing page.
- **Shadows:** near-flat in the app (light theme at or below 6% opacity). Hairline borders do the structure.

## Motion
- **In the app:**
  - Only motion that explains a change: row expand, toast, panel slide or timeline reveal.
  - 150-250ms, using the spring and easing values from apple-design.
  - No scroll-triggered entry animation in the console.
- **On the landing page:**
  - GSAP with ScrollTrigger and SplitText (free, all plugins) for the governed-request scroll story and text reveals.
  - One Three.js / WebGL ring, a quiet background behind the hero, lazy-loaded after first paint with `React.lazy` and an `IntersectionObserver`. Static poster fallback. It stays only while Lighthouse holds: desktop 90, mobile 75.
  - At most one ambient WebGL background on the whole site. No WebGL anywhere in the app.
- **Reduced motion:** honor `prefers-reduced-motion` everywhere. GSAP timelines go to their end state, and WebGL shows the poster.
- **Performance:** animate `transform` and `opacity` only. `backdrop-blur` only on fixed layers. Landing page Lighthouse performance: desktop 90 or more, mobile 75 or more.

## Components and third-party code
- **Base:** shadcn/ui primitives via the shadcn CLI, restyled to our tokens and never left in default state (taste §9.E).
- **21st.dev:** may supply components through the shadcn registry install. The free tier allows 2 copies a day, so pick deliberately. Put the source URL in a comment at the top of each file.
- **threeui.com:** may supply WebGL sections. Check each item's license first and skip anything paid. Put the source URL and license in a comment.
- **Icons:** Phosphor (`@phosphor-icons/react`), regular weight in the app and light on the landing page. Lucide is retired in new code.

## Bans (from taste §9, applied to every surface)
- No em-dash or en-dash in visible copy. Use a hyphen, a period or a colon.
- No AI-purple gradients, neon glows, pure `#000`, or three equal feature cards.
- No div-built fake product screenshots on the landing page. Use real app screenshots or real components, labelled as example data.
- No filler copy words such as "elevate", "seamless", "unleash" or "next-gen". No fake-perfect numbers, and no version labels in the hero.
- No decorative status dots. A dot is allowed only when it is a real state, such as a live health check.
- No "demo" wording. The mode is `public-preview`, and the platform has no brand name.

## Pre-flight (before any UI change is done)
- [ ] Both light and dark modes are checked, and text passes AA.
- [ ] It works with the keyboard, focus is visible, and Radix primitives keep their ARIA.
- [ ] It works with reduced motion.
- [ ] Empty, loading and error states are present.
- [ ] No hard-coded colors (lint enforces it), no em-dashes and no banned words (`npm run copy-check`).
- [ ] New shared components have a row in `docs/design/COMPONENTS.md`, and new text pairs a row in `docs/design/ACCESSIBILITY.md`.
- [ ] Verdicts use an icon, a word and color together.
- [ ] Tests exist: Vitest + Testing Library for components, and Playwright for flows.

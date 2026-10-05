---
name: governed-design
description: The project design skill for the Governed Agent Platform UI (ui/). Every frontend builder reads and follows it before writing UI code: the console, the workspace, the trust pages and the showcase landing page. It merges the apple-design skill, the taste skill (main, soft and minimalist variants) and docs/UI_GUIDELINES.md, and says which rule wins when they disagree.
---

# Governed design

This skill is the single entry point for UI work in `ui/`. Read it in full, then read the parts of the sources it points to.

## Sources and precedence
When rules conflict, the higher item wins.
1. **Accessibility and honesty.** WCAG AA, keyboard use, `prefers-reduced-motion`, no fake data shown as real.
2. **`docs/UI_GUIDELINES.md`.** The product's tokens, components, states and copy rules.
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
- **Verdict states.** Each one has a token pair (text plus tint), an icon and a word. Never use color alone.
  - **Allow:** `--allow`, check icon, "Allowed".
  - **Deny:** `--deny`, block icon, "Denied", plus the reason code in mono.
  - **Escalate:** `--escalate`, hand icon, "Needs approval".
  - **Unrecorded / unavailable:** `--warning`, "Not recorded".
- **Trace / timeline.** A vertical rail of steps: actor → gateway stage(s) → verdict → receipt (decision id, policy version, input hash). Each step shows a timestamp in mono and its duration. The deny step is the visual anchor of a denied trace. Steps expand inline, not in a modal.
- **Receipt.** Decision id, policy version, tenant, principal, action, resource and the SHA-256 input hash. All monospace, each value copyable. The raw input text is never shown, because the platform does not store it.
- **Secrets.** Key screens show the prefix, scopes, created and last-used times only. The one-time secret appears once, in a copy-once dialog, and is never fetched again.
- **Empty, loading and error states** exist for every screen.
  - Loading uses skeletons in the final layout shape, never a centered spinner on a console table.
  - Errors show the API error `code` and `request_id`, with a retry action.
  - Empty states say what would appear there and how to make it appear.
- **Density switch.** Console tables have compact rows (32px) by default and a comfortable option (40px). Numbers are right-aligned in tabular figures.

## Tokens
- **Source of truth:** `ui/src/styles/tokens.css`. Tailwind reads the CSS variables (`theme.extend.colors` maps to `var(--…)`), and shadcn components use the same variables. Never hard-code a hex color in a component.
- **Existing tokens:** keep the current brand (Ink Blue), the neutrals and the semantic tokens.
- **Verdict tokens:** add `--allow`, `--deny` and `--escalate`, each with a `-tint`, for light and dark. They must pass AA for text on `--bg-surface`.
- **Typography:**
  - Geist Sans for UI and Geist Mono for ids, hashes and codes, self-hosted from the `geist` npm package (OFL).
  - The taste skill bans Inter as a default, so Inter is retired.
  - Tabular numbers in tables.
- **Radius:** 8px for console cards and inputs, 12px for workspace cards, and up to 24px only on the landing page.
- **Shadows:** near-flat in the app (opacity < 0.06). Hairline borders do the structure.

## Motion
- **In the app:**
  - Only motion that explains a change: row expand, toast, panel slide or timeline reveal.
  - 150-250ms, using the spring and easing values from apple-design.
  - No scroll-triggered entry animation in the console.
- **On the landing page:**
  - GSAP with ScrollTrigger and SplitText (free, all plugins) for the governed-request scroll story and text reveals.
  - One Three.js / WebGL hero, lazy-loaded after first paint with `React.lazy` and an `IntersectionObserver`. Static poster fallback.
  - At most one ambient WebGL background on the whole site. No WebGL anywhere in the app.
- **Reduced motion:** honor `prefers-reduced-motion` everywhere. GSAP timelines go to their end state, and WebGL shows the poster.
- **Performance:** animate `transform` and `opacity` only. `backdrop-blur` only on fixed layers. Landing page Lighthouse performance ≥ 85 (desktop).

## Components and third-party code
- **Base:** shadcn/ui primitives via the shadcn CLI, restyled to our tokens and never left in default state (taste §9.E).
- **21st.dev:** may supply components through the shadcn registry install. The free tier allows 2 copies a day, so pick deliberately. Put the source URL in a comment at the top of each file.
- **threeui.com:** may supply WebGL sections. Check each item's license first and skip anything paid. Put the source URL and license in a comment.
- **Icons:** Phosphor (`@phosphor-icons/react`), regular weight in the app and light on the landing page. Lucide is retired in new code.

## Bans (from taste §9, applied to every surface)
- No em-dash or en-dash in visible copy. Use a hyphen, a period or a colon.
- No AI-purple gradients, neon glows, pure `#000`, or three equal feature cards.
- No div-built fake product screenshots on the landing page. Use real app screenshots or real components.
- No filler copy words such as "elevate", "seamless", "unleash" or "next-gen". No fake-perfect numbers, and no version labels in the hero.
- No decorative status dots. A dot is allowed only when it is a real state, such as a live health check.
- No "demo" wording. The mode is `public-preview`, and the platform has no brand name.

## Pre-flight (before any UI change is done)
- [ ] Both light and dark modes are checked, and text passes AA.
- [ ] It works with the keyboard, focus is visible, and Radix primitives keep their ARIA.
- [ ] It works with reduced motion.
- [ ] Empty, loading and error states are present.
- [ ] No hard-coded colors, no em-dashes and no banned words.
- [ ] Verdicts use an icon, a word and color together.
- [ ] Tests exist: Vitest + Testing Library for components, and Playwright for flows.

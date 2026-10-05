# Sprint 005b: Polish round. Requirements

A vertical slice on top of Sprint 005. The decisions are settled in the Architect's plan: name, audience, landing copy, hero, ink-and-paper color, and scope. This pack turns them into a contract and checks. It is not a new design debate.

## Settled inputs
- **Name.** It stays descriptive: "Governed Agent Platform".
- **Audience.** The landing page speaks first to the person accountable for the agents (team lead, owner, risk owner). Engineers come second.
- **Headline:** "Your agents can only ever do less." It is the only loud element.
- **Subline:** "Control what your agents can do. See everything they did."
- **Hero:** real console components with example data, showing a receipt being issued and a denied call. The WebGL ring is optional. It's kept only as a quiet background, and dropped if it doesn't earn its cost.
- **Mechanism depth.** The landing page gives one plain line per capability. The detail goes on a "How it works" page.
- **No problem section.** The story shows the problem.
- **Use-cases strip.** Only what exists today:
  - an internal knowledge assistant over company documents
  - an agent with tool access
  - a team that must see what its agents did
- **One "why outside the agent" point:** checks inside agent code can be skipped or changed by that code. A gateway sits outside, so every call is checked.
- **Claims** stay within the "may claim" list in `planning/FRONTEND_STATE.md` §6. There is nothing about approvals, signed receipts, scale or customers.
- **Color: ink and paper.** Warm paper neutrals and near-black ink. Verdict colors are the only strong color. One rare seal color (deep petrol) is used for the logo dot, links, focus rings and a few landing highlights. Primary buttons are ink. There is one accent only. The starting values are in `blueprint.md` §4.

## Scope
1. **Landing page:** the copy, hero and sections above. A new public route `/how-it-works`.
2. **Overview** (`/app`, the console home):
   - The numbers: checked, blocked, deny rate, budget used, and the top deny reasons.
   - Each number links to its filtered records.
3. **Decisions grouped by request.** The table lists requests. A slide-over drawer shows that request's decisions and the stage trace.
4. **Deny is the loudest state:**
   - the failing stage in red
   - a plain sentence
   - the policy field and the policy version behind it
5. **Plain-language reasons.** One catalogue, served by the API and used everywhere in the UI.
6. **Governance line under each answer in Ask**, for example "Checked by policy v3 · 2 checks · allowed". It links to the request.
7. **Guided walkthrough.** This is the first experience for visitors.
   - It runs one allowed and one blocked request against the real API, then shows both decisions side by side.
   - The blocked one is stopped by the input guardrails, which every tenant has, so it works without extra setup.
   - It is called a walkthrough. No "demo" wording.
8. **Navigation:** a session menu (who you are, tenant, scopes, sign out, theme) and a Cmd+K command palette (go to a screen, find a request id).
9. **Ink-and-paper tokens** across `tokens.css`, `docs/UI_GUIDELINES.md` and `.claude/skills/governed-design/SKILL.md`.
10. **Polish pass** on the hand-built components: consistent radii, focus, hover, density, empty, loading and error states.
11. **Route-level code splitting.**
12. **Mobile Lighthouse** on the landing page, where the environment allows it.

## Out of scope
- Anything in Sprints 006–010.
- Approvals.
- Editing policies or keys.

## Standard design documentation (added by the Architect)
Design decisions live in established, versioned files, not only in briefs and code. These follow common industry practice:
- design tokens in a standard format with one source of truth
- separate foundation, content and accessibility documents
- a component inventory
- ADRs for decisions that are hard to reverse

13. **Design tokens as data.** `ui/tokens/tokens.json` in the W3C Design Tokens Community Group format (`$value`, `$type`, `$description`; color, dimension, fontFamily, duration, cubicBezier). It's the single source of truth.
    - `ui/src/styles/tokens.css` is generated from it with Style Dictionary (v4, which reads this format).
    - A CI step regenerates it and fails on drift.
    - Light and dark are two token sets.
14. **`docs/design/` as the design doc set.** `docs/UI_GUIDELINES.md` becomes a short index that points into it, and keeps its history section. The files:
    - `README.md`: what each document covers, who owns it, and the precedence order (accessibility and honesty, then these docs, then the design skill).
    - `DESIGN_SYSTEM.md`: the foundations.
      - Identity: the descriptive name, the logo mark, and the seal's rules.
      - Color roles and the contrast table.
      - Type scale, spacing, radius, elevation and motion.
      - The two surfaces (console and workspace) and the landing page.
    - `CONTENT_STYLE.md`: the content rules.
      - Voice and tone, and the audience order.
      - A glossary of product terms: decision, receipt, request, policy, policy version, tenant, principal, scope, knowledge base, verdict, stage.
      - How reason sentences are written.
      - The may-claim and must-not-claim lists, moved here from `planning/FRONTEND_STATE.md`.
      - The banned words and characters.
    - `ACCESSIBILITY.md`: the target, WCAG 2.2 level AA. How it's tested (axe in Playwright, keyboard paths, reduced motion, both themes). The known exceptions, and how to report a new one.
    - `COMPONENTS.md`: an inventory of every shared component, with purpose, variants, states, accessibility notes and its test file.
    - `PATTERNS.md`: the governance patterns. Verdict, trace, receipt, deny emphasis, governance line, empty, loading and error states, and the request drawer.
15. **ADR-0010: design tokens and the ink-and-paper palette.**
    - Context: the blue was generic, and governance must be the most visible thing on screen.
    - Decision: ink and paper, one seal color, verdicts as the only strong color, and tokens in DTCG JSON.
    - Consequences, and when to revisit. ADR-0008 and ADR-0009 stay reserved for the event bus and the agent runtime.
16. **Guard rails in code.**
    - An ESLint rule (or a test) fails on hex, rgb or hsl color literals in `ui/src` outside the generated tokens file.
    - A test checks that every color pair listed in `ACCESSIBILITY.md` meets AA.
17. **The design skill points to these docs.** `.claude/skills/governed-design/SKILL.md` stays the agent-facing entry point, and links to `docs/design/` as the source.

Storybook is the usual component catalogue, but it isn't in this sprint. It adds a large toolchain. `COMPONENTS.md` plus the Vitest tests cover the need for now. See Q14.

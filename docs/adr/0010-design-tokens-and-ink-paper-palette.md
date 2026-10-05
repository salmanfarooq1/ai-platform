# ADR 0010: Design tokens and the ink-and-paper palette

**Status:** Accepted

ADR-0008 and ADR-0009 stay reserved for the event bus and the agent runtime.

## Context
The UI of Sprint 005 used a blue accent (`#2F5BEA` in light, `#6E8BFF` in dark). Blue is the default color of generic software. It said nothing about this product, and it competed with the verdict colors for attention. For a governance product, the most visible thing on screen must be whether a call was allowed or denied, and why.

The design rules were also spread over prose: `docs/UI_GUIDELINES.md` held the token tables by hand, and `ui/src/styles/tokens.css` was edited by hand. Nothing checked that the two agreed, or that a component did not bring its own color.

## Decision
- **Ink and paper.** Warm paper neutrals and near-black ink for all structure. Light values start at `#F6F4EF` (page) and `#FDFCFA` (surface). Dark values start at `#131312` and `#1C1B19`. Primary buttons are ink.
- **One seal color.** Deep petrol (`#0B5D6E` in light, `#5DB7C4` in dark). It is used for the logo dot, links, focus rings and a few quiet highlights on the landing page. It is never a button fill, a verdict or a chart color. There is no second accent. The old brand blue is removed.
- **Verdicts are the only strong color.** Allow green, deny red and escalate amber keep their tokens. A verdict always shows an icon, a word and a color.
- **Tokens are data.** `ui/tokens/tokens.json` is the single source of truth, in the W3C Design Tokens Community Group format (`$value`, `$type`, `$description`). Light and dark are two token sets with the same roles. Style Dictionary v4 generates `ui/src/styles/tokens.css` through `npm run tokens`. CI regenerates the file and fails on any difference.
- **Guard rails in code.** ESLint fails on a hex, rgb or hsl literal in `ui/src` outside the generated file. A Vitest test does the same for stylesheets. A contrast test reads the pairs listed in `docs/design/ACCESSIBILITY.md` and checks each against the tokens in both themes.
- **Docs.** The design documents live in `docs/design/`. `docs/UI_GUIDELINES.md` is an index that keeps the history.

## Consequences
- Governance is the most visible thing on screen. A calm page has no strong color, and a denial stands out at once.
- A change of palette is a change to one JSON file, plus the contrast table. The generated CSS, Tailwind and the tests follow.
- A new color needs a token and a row in the contrast table. A component cannot sneak one in.
- Style Dictionary and its dependencies are now dev dependencies of `ui/`.
- The seal is a low-contrast personality: it is rare on purpose. If a screen needs more emphasis, use a verdict color or weight, not the seal.
- Dark-theme shadows are a little stronger than the light-theme rule of 6% opacity, because shadows on a dark page need more to show.
- The Lighthouse targets for the landing page are tied to the WebGL ring. If the scores fall under the targets, the ring is removed.

## Revisit when
- The platform gets a name and a visual identity (open question 1 in `planning/FRONTEND_STATE.md`). The seal color and the logo mark may change then.
- Escalate (needs approval) is built, because the amber token becomes a live state and may need more emphasis.
- A human review of the screens finds the seal too quiet or the paper too warm. Values are a builder's call and can change inside this decision.
- A second surface needs its own accent. That would need a new ADR.

## Alternatives considered
- **Keep the blue and add the verdict colors:** simple, but generic, and it kept two things fighting for attention.
- **A second neutral accent for the console:** more variety, but it dilutes the one-accent rule and adds a color to test in both themes.
- **Hand-edited CSS variables:** no new toolchain, but nothing keeps the docs, the CSS and the tests in step.
- **Tokens only in Tailwind config:** close to the code, but not a standard format and not readable by design tools.
- **Storybook for the component catalogue:** the usual choice, left out for now because of its large toolchain. See Q14.

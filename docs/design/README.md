# Design documentation

This folder is the source of truth for how the web UI in `ui/` looks, reads and behaves. The design skill (`.claude/skills/governed-design/SKILL.md`) is the short entry point for agents. It links here.

## The documents
| File | What it covers | Owner |
|---|---|---|
| `DESIGN_SYSTEM.md` | Foundations: identity, color roles, type, spacing, radius, elevation, motion, and the three surfaces | The frontend builder of each sprint |
| `CONTENT_STYLE.md` | Voice, audience order, the glossary, how reason sentences are written, the may-claim and must-not-claim lists, banned words and characters | The architect, who signs off claims |
| `ACCESSIBILITY.md` | The WCAG 2.2 AA target, how it is tested, the contrast pairs, known exceptions | The frontend builder |
| `COMPONENTS.md` | An inventory of every shared component, with its variants, states, accessibility notes and test file | The frontend builder |
| `PATTERNS.md` | The governance patterns: verdict, trace, receipt, deny emphasis, governance line, empty, loading and error states, the request drawer | The frontend builder |

The design tokens are data, not prose. They live in `ui/tokens/tokens.json` (W3C Design Tokens format). `ui/src/styles/tokens.css` is generated from that file by `npm run tokens`. CI fails if the two differ.

## Three rules that do not bend
1. **Every answer shows its evidence.** Citations, confidence and the verdict sit next to the answer.
2. **Every call leaves a receipt.** The UI can open the decision behind any answer. It never shows the input text, because the platform does not store it.
3. **Nothing waits for no reason.** Feedback starts on press. Motion can be interrupted. There are no artificial delays.

## Precedence
When two sources disagree, the higher one wins.
1. **Accessibility and honesty.** WCAG AA, keyboard use, reduced motion, and no made-up data shown as real.
2. **These documents.**
3. **The design skill** and the sources it merges (motion rules, anti-generic rules).

## Changing a document
- A change to a token goes in `tokens.json`. Run `npm run tokens`. Update the contrast table in `ACCESSIBILITY.md` if a text pair changes. The contrast test reads that table.
- A new shared component gets a row in `COMPONENTS.md` and a test file.
- A new claim on a public page needs an item on the may-claim list first. See `CONTENT_STYLE.md`.
- A decision that is hard to reverse gets an ADR in `docs/adr/`. The palette decision is ADR-0010.

The history of the earlier UI guideline versions is in `planning/history/UI_GUIDELINES.md`.

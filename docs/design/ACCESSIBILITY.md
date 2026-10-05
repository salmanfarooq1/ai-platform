# Accessibility

**Owner:** the frontend builder of each sprint. **Target:** WCAG 2.2 level AA, in both themes.

Accessibility and honesty come first in the precedence order (see `README.md`). A design rule never overrides them.

## How it is tested
- **axe in Playwright** (`ui/e2e/a11y.spec.ts`). It scans the landing page, How it works, Overview, Requests with the drawer open and the walkthrough, in the light and dark theme. The sprint passes with 0 serious or critical violations. Moderate and minor findings are logged in the test output and are fixed when they are cheap.
- **Contrast test** (`ui/src/styles/contrast.test.ts`). It reads the pair table below and checks every pair against `ui/tokens/tokens.json` for both themes. A pair that falls under its minimum fails the build.
- **Keyboard paths** (Playwright). Cmd or Ctrl plus K opens the palette, arrow keys and Enter pick a result, Escape closes the palette and the drawer, and the session menu opens from the keyboard.
- **Reduced motion** (Playwright, `landing.spec.ts`). With `prefers-reduced-motion: reduce` there is no GSAP, no WebGL, the poster is shown and every story step is visible.
- **Both themes.** Every axe scan runs twice.
- **Component tests** (Vitest and Testing Library) check roles, names, `aria-current`, `aria-selected` and that a verdict never relies on colour alone.

## Rules in force
- A verdict always shows an icon, a word and a colour.
- Every interactive element has a visible focus ring in the seal colour.
- Radix primitives keep their ARIA. Dialogs trap focus and Escape closes them.
- Tables have a caption, column headers with `scope`, and numbers in tabular figures.
- Charts have a text alternative and a hidden table with the same numbers.
- Errors show the API error code and request id, and offer a retry.
- Text that is not decoration is at least 4.5:1. The pairs below are the ones the product uses.

## Contrast pairs
The test reads the rows of this table. A background with transparency is painted over `bg-surface` of the same theme first. To add a pair, add a row.

| Foreground | Background | Minimum | Where it is used |
|---|---|---|---|
| `text-primary` | `bg-canvas` | 4.5 | Body text on the page |
| `text-primary` | `bg-surface` | 4.5 | Text on cards, tables and drawers |
| `text-primary` | `bg-muted` | 4.5 | Text in inputs and table heads |
| `text-primary` | `bg-selected` | 4.5 | Text in a selected row or active nav item |
| `text-secondary` | `bg-selected` | 4.5 | Secondary text in a selected row or the active palette option |
| `text-tertiary` | `bg-selected` | 4.5 | Quiet labels in a selected row |
| `text-secondary` | `bg-canvas` | 4.5 | Secondary text on the page |
| `text-secondary` | `bg-surface` | 4.5 | Secondary text on cards |
| `text-secondary` | `bg-muted` | 4.5 | Secondary text in inputs and table heads |
| `text-tertiary` | `bg-canvas` | 4.5 | Placeholders and hints on the page |
| `text-tertiary` | `bg-surface` | 4.5 | Placeholders and hints on cards |
| `text-tertiary` | `bg-muted` | 4.5 | Placeholders in inputs |
| `text-on-ink` | `ink` | 4.5 | Label on a primary button |
| `text-on-ink` | `ink-hover` | 4.5 | Label on a hovered primary button |
| `seal` | `bg-canvas` | 4.5 | Links on the page |
| `seal` | `bg-surface` | 4.5 | Links on cards, and the focus ring |
| `seal` | `bg-muted` | 4.5 | Links on quiet fills |
| `seal` | `bg-selected` | 4.5 | Links in a selected row |
| `allow` | `bg-surface` | 4.5 | Allowed verdict text |
| `deny` | `bg-surface` | 4.5 | Denied verdict text |
| `escalate` | `bg-surface` | 4.5 | Needs-approval verdict text |
| `allow` | `allow-tint` | 4.5 | Allowed badge |
| `deny` | `deny-tint` | 4.5 | Denied badge and the deny callout heading |
| `escalate` | `escalate-tint` | 4.5 | Needs-approval badge |
| `text-primary` | `deny-tint` | 4.5 | Sentence in the deny callout |
| `text-secondary` | `deny-tint` | 4.5 | Labels in the deny callout |
| `deny` | `bg-muted` | 4.5 | Deny text on a quiet fill |

## Known exceptions
- **Hairlines and input fills.** Borders and the `bg-muted` fill of an input are below 3:1 against the card. The input is identified by its label, its placeholder and its focus ring, which passes. This is accepted for the quiet look of the console.
- **The WebGL ring on the landing page.** It is decorative, sits behind the hero at low opacity, and is hidden from assistive technology. axe cannot measure text over a canvas, so the hero text is checked against the page background instead.
- **Third-party widgets.** None are used.

## How to report a new exception
Add a line under "Known exceptions" in the same change that introduces it. Say what fails, which criterion, who is affected, why it is accepted and what would remove it. An exception without that line is a bug.

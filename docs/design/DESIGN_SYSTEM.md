# Design system

The foundations of the UI. Values come from `ui/tokens/tokens.json`. This file explains what they are for.

## Identity
- **Name.** The product is called "Governed Agent Platform". That is a description, not a brand. Names belong only to use cases built on top.
- **Logo mark.** A rounded square in ink with three light lines. The last line is shorter and ends in a dot. The dot is the seal color. Component: `LogoMark` and `Logo`.
- **Feeling.** Ink and paper. Warm paper neutrals, near-black ink, and verdict colors as the only strong color. Calm, exact and trust-first.

### The seal
There is one accent, called the seal (deep petrol). It marks "this is where governance is".
- **Use it for:** the dot in the logo, links, focus rings, and a few quiet highlights on the landing page.
- **Never use it for:** buttons, verdicts, charts, backgrounds of large areas, or decoration.
- **Primary buttons are ink**, not seal.
- There is no second accent. The old brand blue is removed.

## Color
Light and dark are two token sets with the same roles. Every role is defined in both.

| Role | Token | Light | Dark | Used for |
|---|---|---|---|---|
| Page | `bg-canvas` | `#F6F4EF` | `#131312` | Page background (warm paper, never pure white or black) |
| Surface | `bg-surface` | `#FDFCFA` | `#1C1B19` | Cards, tables, drawers, dialogs |
| Muted | `bg-muted` | `#EFECE5` | `#242320` | Inputs, table heads, code blocks |
| Selected | `bg-selected` | ink at 6% | ink at 8% | Selected row, active nav item |
| Hairline | `hairline` | `#E3DFD6` | `#2D2B27` | Borders and dividers |
| Ink | `ink` | `#18181B` | `#ECEAE4` | Primary button fill, logo container |
| Text | `text-primary` | `#18181B` | `#ECEAE4` | Body and headings |
| Muted text | `text-secondary` | `#5E5B55` | `#A39F97` | Supporting copy |
| Quiet text | `text-tertiary` | `#6B675F` | `#9A968E` | Hints, placeholders, metadata |
| Seal | `seal` | `#0B5D6E` | `#5DB7C4` | See above |
| Allow | `allow` | `#146B41` | `#4CD38A` | Allowed verdict |
| Deny | `deny` | `#BF2A22` | `#FF7A72` | Denied verdict and the deny emphasis |
| Escalate | `escalate` | `#8F5600` | `#F2B04A` | Needs-approval verdict (designed, not built) |

Each verdict has a `-tint` token. A tint is painted over `bg-surface`, never over whatever is behind the element. `success`, `warning` and `danger` are aliases of allow, escalate and deny, kept for confidence chips.

**Rules**
- Color is never the only signal. A verdict shows an icon, a word and a color.
- Verdict colors are the only strong color on the page. A calm screen has none.
- Text pairs are listed with their ratios in `ACCESSIBILITY.md`. A test checks them in both themes.
- Never write a color literal in a component. Use a token. ESLint fails on hex, rgb and hsl literals outside the generated tokens file.

## Type
Geist Sans for the UI. Geist Mono for ids, hashes, reason codes, policy keys and JSON.

| Token | Size | Leading | Tracking | Use |
|---|---|---|---|---|
| `display` | 2.25rem to 3.25rem (fluid) | 1.05 | -0.025em | Landing headline only |
| `title-1` | 1.75rem | 1.15 | -0.02em | Page titles and stat values |
| `title-2` | 1.25rem | 1.25 | -0.012em | Section titles |
| `headline` | 1rem | 1.35 | -0.006em | Card titles |
| `body` | 0.9375rem | 1.55 | 0 | Answers and prose |
| `callout` | 0.875rem | 1.45 | 0 | Controls and supporting copy |
| `footnote` | 0.8125rem | 1.4 | 0.005em | Table cells and metadata |
| `caption` | 0.6875rem | 1.3 | 0.06em | Uppercase labels only |

Sentence case everywhere. Numbers in tables and stats use tabular figures.

## Spacing
A 4px base: 4, 8, 12, 16, 20, 24, 32, 40, 48. Layout tokens: sidebar 248px, top bar 56px, drawer 520px. Console table rows are 32px (compact, default) or 40px (comfortable). The choice is remembered in this browser.

## Radius
| Token | Value | Where |
|---|---|---|
| `radius-sm` | 8px | Console cards, inputs, buttons, table frames |
| `radius-md` | 12px | Workspace cards and dialogs |
| `radius-lg` | 16px | Large panels |
| `radius-xl` | 24px | Landing page only |
| `radius-full` | 9999px | Badges and chips |

## Elevation
The app is near flat. Hairline borders do the structure. Light-theme shadows stay at or below 6% opacity. Dark-theme shadows are a little stronger, because black on a dark page needs more to show at all. Overlays (dialog, drawer, palette) rely on a scrim. A translucent layer is used only on fixed bars (sidebar, top bar, landing header), with a 24px blur, and it never sits on another translucent layer.

## Motion
| Token | Value | Use |
|---|---|---|
| `motion-duration-press` | 100ms | Press feedback, scale to 0.97 |
| `motion-duration-fast` | 150ms | Hover and color changes |
| `motion-duration-base` | 200ms | Theme change, fades |
| `motion-duration-slow` | 250ms | Drawer slide |
| `motion-ease-out` | cubic-bezier(0.2, 0, 0, 1) | Default |

- In the app, only motion that explains a change: a drawer sliding, a row expanding, a toast. Animate `transform` and `opacity` only. No scroll-triggered entry animation.
- On the landing page: GSAP scroll story and heading reveals. At most one ambient WebGL background on the whole site, and none in the app.
- `prefers-reduced-motion`: no GSAP, no WebGL, a static poster, and every story step visible.

## The surfaces
| Surface | Routes | Character | Dials (variance, motion, density) |
|---|---|---|---|
| Console | Overview, Requests, Decisions, Policies, Keys, Usage, Agent runs | Dense, quiet, exact. Tables, filters, timelines | 3, 2, 7 |
| Workspace | Walkthrough, Ask, Library, History | Calm. The answer and its evidence are the loudest thing | 4, 3, 4 |
| Trust and System | Trust, System | Plain and factual | 3, 2, 5 |
| Landing | `/`, `/how-it-works` | Editorial. The headline is the only loud element | 7, 6, 3 |

On the landing page the hero is built from the real console components with example data, labelled as examples. There are no fake screenshots made of boxes. The WebGL ring is a quiet background behind the hero, kept only while the Lighthouse targets hold (desktop 90, mobile 75).

## Tokens in the build
1. Edit `ui/tokens/tokens.json`. It uses `$value`, `$type` and `$description`, with the types color, dimension, fontFamily, duration, cubicBezier, number and shadow.
2. Run `npm run tokens` in `ui/`. Style Dictionary v4 writes `ui/src/styles/tokens.css`: theme-free tokens in `:root`, the light set, the dark set under the OS setting, and the explicit `[data-theme]` selectors.
3. Tailwind maps its colors, radii and type to those CSS variables in `ui/tailwind.config.ts`.
4. CI runs the generator and fails on any difference.

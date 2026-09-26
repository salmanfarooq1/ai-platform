# Verity — Product Branding Guidelines

> Version 1.0.0 · September 2026
> Authoritative reference for the ai-platform web UI (`ui/`).
> Built on the `apple-design` skill (`.claude/skills/apple-design/SKILL.md`). Section numbers in brackets, like [§12], point to that skill.

---

## Overview

Verity is a retrieval and reasoning workspace. People ask questions about their documents. Verity answers with citations, a confidence level, and a record of how it got there.

The whole brand serves one feeling: **calm confidence**. Every answer should look traceable, not magical.

**Three non-negotiable rules:**

1. **Every answer shows its evidence.** Citations, confidence and verification status sit next to the answer, never hidden behind a click.
2. **Content first, chrome second.** Navigation and toolbars are light, translucent layers. The answer is the loudest thing on screen.
3. **Nothing waits for no reason.** Feedback starts on press. Motion is interruptible. No artificial delays.

---

## 1. Name & Tagline

| Property | Value |
|---|---|
| **Product name** | Verity |
| **Tagline** | Answers you can trace. |
| **Capitalisation** | Title case name. Sentence case tagline. |
| **Page `<title>`** | `Verity — <Page name>` (e.g. `Verity — Ask`) |
| **Hero headline** | `Answers you can <em>trace</em>.` |

The accent word in a hero headline is always the **verb that proves trust**: *trace*, *verify*, *cite*. It is set in italic and in Brand Ink Blue.

The name and tagline live in one config object (`ui/src/brand.js`). Never hardcode them in components.

---

## 2. Logo

### Logo mark

A **rounded square with three stacked lines**, where the last line is shorter and ends in a dot. It reads as "a paragraph, with its source marked."

```
┌─────────┐
│ ─────── │
│ ─────── │
│ ────  ● │   ← dot: Brand Ink Blue
└─────────┘
```

| Property | Value |
|---|---|
| Container | 32 × 32 px, radius 9 px |
| Container fill | `--ink` (near-black in light, near-white in dark) |
| Lines | Inverse of container, stroke 2, round caps |
| Dot | `--brand` (Ink Blue) — the only decorative use of the brand color |
| SVG viewBox | `0 0 24 24` |

### Lockup

```
[mark]  Verity
        ANSWERS YOU CAN TRACE
```

| Element | Style |
|---|---|
| Name | 15px, weight 700, tracking `-0.01em` |
| Tagline | 10px, weight 600, uppercase, tracking `0.06em`, `--text-tertiary` |
| Gap | 10px |

Collapsed sidebar or mobile top bar: mark only.

---

## 3. Mode Badge

The platform runs in modes (`demo`, `local`, `prod`) from `/config`. A small pill in the sidebar and on the Overview page shows the mode, so people know what they are talking to.

| Mode | Dot color | Meaning |
|---|---|---|
| Demo | Amber `--warning` | Free tier, reduced pipeline (no reranker) |
| Local | Blue `--brand` | Developer machine |
| Production | Green `--success` | Full pipeline |

Pill: radius full, 1px `--hairline` border, translucent `--material-thin` fill, 11px weight 600 uppercase text, tracking `0.06em`.

---

## 4. Color

Apple-style color: neutral, adaptive to light and dark, with one quiet brand color. Color carries **meaning**, not decoration.

### Brand

| Token | Light | Dark | Role |
|---|---|---|---|
| `--brand` | `#2F5BEA` | `#6E8BFF` | Primary action, focus ring, links, selected state, logo dot |
| `--brand-pressed` | `#2449C4` | `#5A77EE` | Primary button while pressed |
| `--brand-tint` | `rgba(47,91,234,0.10)` | `rgba(110,139,255,0.16)` | Selected rows, active nav fill, highlighted citation |
| `--ink` | `#0B0D12` | `#F3F4F6` | Logo container, strongest text |

### Neutrals (surfaces)

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg-canvas` | `#F6F6F4` | `#0E0F12` | Page background (warm off-white / soft black, never pure) |
| `--bg-surface` | `#FFFFFF` | `#16181D` | Cards, panels, modals |
| `--bg-muted` | `#F0F0EE` | `#1C1F25` | Inputs, code blocks, table headers |
| `--material-thin` | `rgba(255,255,255,0.62)` | `rgba(22,24,29,0.62)` | Translucent sidebar, top bar, toolbars |
| `--hairline` | `rgba(0,0,0,0.07)` | `rgba(255,255,255,0.08)` | Every border and divider |
| `--text-primary` | `#0B0D12` | `#F3F4F6` | Body and headings |
| `--text-secondary` | `#565B66` | `#A3A8B3` | Supporting copy |
| `--text-tertiary` | `#8B909B` | `#6F7480` | Labels, metadata, timestamps |

### Semantic

Apple's four feedback kinds [§16]: status, completion, warning, error. Each has one color.

| Token | Light | Dark | Used for |
|---|---|---|---|
| `--success` | `#1F9D55` | `#34C77B` | Verified answers, ingest complete, healthy service |
| `--warning` | `#C27C0E` | `#F0A93B` | Low confidence, partial verification, demo mode |
| `--danger` | `#D6362F` | `#FF6961` | Errors, guardrail blocks, failed ingest |
| `--info` | `--brand` | `--brand` | In-progress status, neutral notices |

### Confidence scale

Retrieval confidence and verification scores map to one scale everywhere (gauge, badges, citation cards, analytics).

| Range | Label | Color |
|---|---|---|
| 0.75 – 1.00 | HIGH | `--success` |
| 0.50 – 0.74 | MEDIUM | `--warning` |
| 0.00 – 0.49 | LOW | `--danger` |

Gauges and progress bars always use the scale color on a `--bg-muted` track. Never gray.

### Color rules

- Color is never the only signal. Pair it with a label or icon.
- Put color on solid layers, not on translucent materials [§12].
- Theme changes ease over 200ms. No abrupt brightness jumps [§14].

---

## 5. Typography

**One family: Inter** (variable, with optical sizing). Mono: **JetBrains Mono** for IDs, chunk text and code. No display serif. Apple defaults to the system face; Inter is the closest cross-platform match, and falls back to `system-ui` [§15].

```css
--font-sans: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
--font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
```

### Type scale

Tracking and leading change with size [§15]. Large text is tight. Small text is slightly open. All sizes are in `rem` so the user's text-size setting scales the layout.

| Token | Size | Weight | Leading | Tracking | Use |
|---|---|---|---|---|---|
| `display` | `clamp(2.25rem, 4vw, 3.25rem)` | 700 | 1.05 | `-0.025em` | Hero headline on Ask page only |
| `title-1` | `1.75rem` | 700 | 1.15 | `-0.02em` | Page titles |
| `title-2` | `1.25rem` | 600 | 1.25 | `-0.012em` | Section titles, modal titles |
| `headline` | `1rem` | 600 | 1.35 | `-0.006em` | Card titles |
| `body` | `0.9375rem` | 400 | 1.55 | `0` | Answers, prose, user content |
| `callout` | `0.875rem` | 400 | 1.45 | `0` | Supporting copy |
| `footnote` | `0.8125rem` | 500 | 1.4 | `0.005em` | Metadata, table cells |
| `caption` | `0.6875rem` | 600 | 1.3 | `0.06em` | UPPERCASE labels, badges |

### Casing rules

- **Sentence case** for buttons, nav items, titles and body. This is the Apple convention: calm, readable.
- **UPPERCASE only for `caption`**: micro-labels, badges, table headers, the tagline.
- Never uppercase user content, answers or document text.
- Emphasis uses **weight**, not size or color [§15].
- Numbers in stats and tables use `font-variant-numeric: tabular-nums`.

---

## 6. Information Architecture

The old UI had six flat tabs (Dashboard, Search, Agent, Ingest, Analytics, Documents). Two pairs were the same job split in two. Nav labels should name their contents, not vague umbrellas [§16 Wayfinding].

### New navigation — four destinations

| Nav item | Route | Icon (Lucide) | Contains | Replaces |
|---|---|---|---|---|
| **Ask** | `/` | `MessageSquareText` | One question box with a mode switch: *Quick answer* (RAG search) or *Deep research* (multi-step agent with verification) | Search + Agent |
| **Library** | `/library` | `Library` | Searchable, paginated documents table. "Add documents" opens an upload modal. | Documents + Ingest |
| **Insights** | `/insights` | `ChartNoAxesColumn` | Cost, usage, latency and answer quality over time | Analytics |
| **System** | `/system` | `Activity` | Service health, uptime, mode, embedding status, version | Dashboard |

- Ask is the home page because asking is the product's purpose [§16 Purpose].
- Old routes redirect: `/search` and `/agent` → `/`, `/ingest` and `/documents` → `/library`, `/analytics` → `/insights`, `/dashboard` → `/system`.
- The namespace selector (e.g. `kyc_aml`, `legal`) lives once, in the top bar, as a "Collection" picker. Every page reads it. It is not repeated in each form.
- The sidebar shows a small health dot next to **System** when a service is down. Wayfinding: problems are visible from anywhere.

### Wayfinding checklist (every page)

- Where am I? Page title plus active nav item.
- What's here? One line of supporting copy under the title.
- Where can I go? Sidebar always visible on desktop.
- How do I get out? Every modal has a close button, `Esc`, and a Cancel action.

---

## 7. Layout

### App shell

```
┌───────────────┬──────────────────────────────────────────────┐
│ [Logo lockup] │  Top bar (translucent): Collection ▾   Theme │
│               ├──────────────────────────────────────────────┤
│ ● DEMO        │                                              │
│               │   Page title                                 │
│ Ask           │   Supporting line                            │
│ Library       │                                              │
│ Insights      │   [ content column, max 1080px, centered ]   │
│ System   ●    │                                              │
│               │                                              │
│ v1.x.x        │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

| Region | Standard |
|---|---|
| Sidebar | 248px, `--material-thin` + `backdrop-filter: blur(24px) saturate(180%)`, right hairline |
| Top bar | 56px, sticky, same translucent material. No hard bottom border: use a soft scroll-edge fade that appears only once content scrolls under it [§12] |
| Content column | `max-width: 1080px`, centered, gutters 40px desktop / 24px tablet / 16px mobile |
| Vertical rhythm | 24px between major blocks, 48px bottom padding |
| Canvas | `--bg-canvas` with the ambient wash (Section 11) |

Below 900px the sidebar becomes a bottom tab bar with the four destinations (icon + label). No horizontal page scroll at any width.

### Ask page layout

```
          ● DEMO · kyc_aml
     Answers you can *trace*.
  Ask anything about your documents.

┌──────────────────────────────────────────┐
│  [ Quick answer | Deep research ]        │  ← segmented control
│                                          │
│  Ask a question…                         │  ← large textarea, 1.125rem
│                                          │
│  Options ▾                       [ Ask ] │  ← advanced options one level deeper
└──────────────────────────────────────────┘
   Try: [chip] [chip] [chip]

┌───────────────────────────┬──────────────┐
│ Answer (markdown)         │ Confidence   │
│                           │ ◔ 0.82 HIGH  │
│                           │ Verified ✓   │
│ [👍 👎 feedback]           │ 1.2s · $0.00 │
└───────────────────────────┴──────────────┘
  Sources (3)
  [citation card] [citation card] [citation card]

  ▸ Reasoning steps (Deep research only, collapsed by default)
```

- Before a question is asked, the hero is centered and the input card sits in the optical middle. After the first answer, the hero shrinks away and the input card docks to the top of the column. Both states use the same element, animated with a spring [§7].
- **Options** (top-k, retrieval mode, rerank, max iterations, verifier) are hidden behind a disclosure. Common path first, advanced one level deeper [§16 Simplicity].

---

## 8. Components

All values below are CSS tokens in `ui/src/styles/tokens.css`. Components use CSS modules.

### Radius

| Token | Value | Use |
|---|---|---|
| `--radius-sm` | 8px | Chips, small icon buttons, inline code |
| `--radius-md` | 12px | Buttons, inputs, nav rows, badges |
| `--radius-lg` | 16px | Cards, citation cards, table container |
| `--radius-xl` | 22px | Ask input card, modals, answer panel |
| `--radius-full` | 9999px | Pills, toggles, avatars, gauges |

Nested corners are concentric: inner radius = outer radius − padding.

### Buttons

| Variant | Style | Use |
|---|---|---|
| Primary | `--brand` fill, white text, 15px weight 600, height 40px, `--radius-md` | One per view: Ask, Upload, Save |
| Secondary | `--bg-muted` fill, `--text-primary` text | Alternative actions |
| Ghost | Transparent, `--text-secondary`, hover `--bg-muted` | Tertiary: Clear, Cancel, Copy |
| Destructive | `--danger` text on ghost; fill only in confirm dialogs | Delete |

- **Press feedback on pointer-down**: `:active { transform: scale(0.97) }` with 100ms ease-out [§1].
- Loading keeps the button's width. Label becomes a spinner plus "Asking…".
- Disabled: 40% opacity, `cursor: not-allowed`.

### Inputs

- `--bg-muted` fill, 1px `--hairline` border, `--radius-md`, 40px height (textarea grows).
- Hover: border darkens slightly. Size never changes.
- Focus: 3px `--brand-tint` ring plus 1px `--brand` border. No layout shift.
- Invalid: `--danger` border and an inline message below. Validate inline, not only on submit [§16].

### Segmented control (Ask mode)

- `--bg-muted` track, `--radius-md`, 2px inset.
- Selected segment is a `--bg-surface` pill with a soft shadow. The pill **slides** between segments with a critically damped spring (`bounce: 0, duration: 0.3`). If the user clicks again mid-slide, it re-targets from the current position [§3].

### Cards

- `--bg-surface`, 1px `--hairline`, `--radius-lg`, padding 20px, shadow `--shadow-sm`.
- No cards inside cards. Group with spacing instead.

### Answer panel

- `--bg-surface`, `--radius-xl`, padding 28px.
- Markdown body in `body` style. Max line length 68ch.
- Inline citation markers `[1]` render as small `--brand-tint` pills. Hovering one highlights its citation card below (and vice versa). Proximity plus mapping [§16].
- Right rail: confidence gauge, verification badge, latency, cost, model.

### Confidence gauge

- Ring, stroke 6, scale color on `--bg-muted` track, value in `title-2` tabular-nums, label in `caption`.
- The ring draws once with a critically damped spring on first reveal. Reduced motion: appears at final value.

### Citation card

- Header: source title (`headline`), page/chunk id (`footnote`, mono), relevance score as a small scale-colored pill.
- Body: excerpt, 3 lines clamped, expandable.
- Selected (linked from answer marker): `--brand-tint` background, `--brand` 1px border.

### Reasoning steps (Deep research)

- Vertical timeline. Each step: small status icon (`Search`, `Brain`, `ShieldCheck`), step name, one-line summary, duration.
- Collapsed by default behind "Show reasoning (N steps)". Expanding uses height spring + opacity.
- While the agent runs, the current step shows a live status line. Ongoing status is always visible [§16].

### Guardrail banner

- Inline in the answer area, not a toast: `--danger` or `--warning` left bar (3px), icon `ShieldAlert`, short title, one line of detail.

### Data table (Library)

- Always has search and pagination (10 / 25 / 50).
- Header row: `caption` style on `--bg-muted`. Rows 48px, hairline dividers, hover `--bg-muted`.
- Right-aligned action column with icon buttons and tooltips.
- Loading, empty, no-results and error states are purpose-built rows. Empty state has a primary "Add documents" button.
- On narrow screens the table scrolls inside its container; the page does not.

### Upload modal (Library → Add documents)

- Opens from the button with `transform-origin` at the button [§7]. Closes back toward it.
- Modal: `--bg-surface`, `--radius-xl`, max-width 560px, dimming scrim `rgba(0,0,0,0.35)`. Page behind does not scroll.
- Body: numbered steps — **1 Choose collection**, **2 Drop files**, **3 Review and upload**.
- Drop zone: dashed `--hairline` border, `--radius-lg`. On drag-over: `--brand-tint` fill and a gentle scale to 1.01.
- Per-file progress rows. Result reported by toast plus an inline summary.
- Focus is trapped. `Esc` closes when not uploading. Focus returns to the trigger.

### Toasts

- Bottom-right on desktop, top-center on mobile (never over the tab bar or primary action).
- `--bg-surface` over a light blur, `--radius-lg`, `--shadow-lg`, 3px semantic left bar plus Lucide icon (`CircleCheck`, `TriangleAlert`, `CircleAlert`, `Info`).
- Success and info auto-dismiss after 4s. Errors stay until dismissed.
- Enter from below with a critically damped spring; exit the same way they came [§7].
- Success: `role="status"`. Warning and error: `role="alert"`.
- No `alert()`, `confirm()` or ad hoc banners for operation results.

### Stat tile (System, Insights)

- Label in `caption`, value in `title-1` tabular-nums, delta or sub-label in `footnote`.
- Status dot for service tiles uses the semantic color plus a text label ("Healthy", "Degraded", "Down").

### Charts (Insights)

- One brand-blue series by default. Additional series use a neutral ramp, not a rainbow.
- Hairline gridlines, `caption` axis labels, tabular numbers, tooltip on hover.
- Quality chart uses the confidence scale colors.

---

## 9. Iconography

- **Lucide React only** (`lucide-react`). No emoji or Unicode glyphs in UI chrome.
- Stroke width 1.75. Icons inherit text color.
- Sizes: nav 18px, buttons 16px, inline labels 14px, empty states 28px.
- Icons sit on the text baseline and are optically centered in buttons.

---

## 10. Depth & Materials

Apple uses translucent layers to show hierarchy [§12].

| Layer | Material | Shadow |
|---|---|---|
| Canvas | `--bg-canvas` + ambient wash | none |
| Sidebar, top bar, tab bar | `--material-thin` + blur 24px, saturate 180% | none, hairline edge |
| Cards | `--bg-surface` (solid) | `--shadow-sm: 0 1px 2px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.03)` |
| Ask card, answer panel | `--bg-surface` (solid) | `--shadow-md: 0 8px 24px -8px rgba(0,0,0,0.10)` |
| Modals, toasts, popovers | `--bg-surface` (solid) | `--shadow-lg: 0 24px 48px -12px rgba(0,0,0,0.18)` |

Rules:

- Bigger surfaces read as thicker: deeper shadow.
- Never put a translucent surface on another translucent surface.
- Modal tasks dim the background. Non-blocking panels (reasoning, filters) do not.
- In dark mode, shadows are weaker; separation comes from a slightly lighter surface and the hairline.
- `prefers-reduced-transparency: reduce` → materials become solid `--bg-surface`, no blur.
- `prefers-contrast: more` → hairlines become `--text-tertiary`, materials solid.

---

## 11. Ambient Background

A quiet atmosphere, never a flat page, and never loud.

- Top wash: linear gradient from `--brand` at 6% (light) / 10% (dark) opacity to transparent, 480px tall, full width.
- Nothing moves. No animated gradients, no looping motion [§14].
- `pointer-events: none`, behind all content.

---

## 12. Motion

Springs, not durations. Critically damped by default [§4].

| Token | Motion (framer-motion / `motion`) | Use |
|---|---|---|
| `spring.default` | `{ type: 'spring', bounce: 0, duration: 0.35 }` | Most UI: panels, docking input card, segmented pill, disclosures |
| `spring.snappy` | `{ type: 'spring', bounce: 0, duration: 0.25 }` | Small elements: toasts, chips, tooltips |
| `spring.momentum` | `{ type: 'spring', bounce: 0.2, duration: 0.4 }` | Only after a flick or drag release (e.g. swiping a toast away) |
| `press` | CSS `transform: scale(0.97)`, 100ms ease-out | Button and row press feedback |

Rules:

- **Feedback on pointer-down**, never only on click [§1].
- **Interruptible**: every animation re-targets from its current value. Never block input during a transition [§3].
- **Symmetric paths**: modals return to the trigger, toasts leave the way they came [§7].
- **Animate only `transform` and `opacity`** [§11].
- List reveals (citations, table rows): stagger 30ms, max 6 items, then the rest appear together.
- No bounce on things that just appear. Bounce only when a gesture carried momentum.
- **`prefers-reduced-motion: reduce`** → replace slides and springs with 150ms opacity cross-fades. Gauges show their final value. Keep color and opacity changes that aid understanding [§14].

---

## 13. Voice & Copy

- Plain, short sentences. No jargon on the surface; technical detail (RRF, rerank, top-k) lives inside Options and tooltips.
- Labels name the thing: "Add documents", not "Submit". "Ask", not "Run query".
- Status copy says what is happening now: "Searching 3 sources…", "Verifying answer…".
- Errors say what happened and what to do: "Upload failed. The file is over 20 MB. Try a smaller file."
- Empty states invite the next step: "No documents yet. Add documents to start asking questions."
- Confidence copy is honest: LOW confidence answers show "Low confidence. Check the sources before relying on this."

---

## 14. Accessibility

- Contrast: body text at least 4.5:1, large text 3:1, in both themes.
- Every interactive element is reachable by keyboard with a visible focus ring (`--brand`, 2px, offset 2px).
- Hit targets at least 40 × 40 px (44 on touch).
- Landmarks: `nav`, `main`, `header`. One `h1` per page.
- Live regions: agent step status and toasts announce politely.
- Respect `prefers-reduced-motion`, `prefers-reduced-transparency`, `prefers-contrast`, and the user's font size.

---

## 15. What's Off-Brand

| ❌ Never | ✅ Instead |
|---|---|
| Emoji or Unicode glyphs as icons (◈ ⌕ ▲) | Lucide icons |
| Pure white `#FFF` or pure black `#000` page | `--bg-canvas` warm off-white / soft black |
| Heavy borders | 1px `--hairline` |
| Hard 1px divider under the sticky top bar | Scroll-edge fade that appears only on scroll |
| Uppercase buttons | Sentence case buttons; uppercase only for captions |
| One fixed `letter-spacing` everywhere | Size-specific tracking from the type scale |
| Linear or fixed-duration CSS animations on interactive elements | Critically damped springs |
| Bounce on menus, modals or toasts that just appear | Bounce only after a flick |
| Feedback only on click / release | Feedback on pointer-down |
| Locking input during a transition | Interruptible, re-targeting motion |
| A modal that opens from the center of the screen | Scales out from its trigger, returns to it |
| Translucent layer stacked on translucent layer | Solid surface over material |
| Gray progress bars or gauges | Confidence scale colors |
| Answers without visible sources or confidence | Evidence always beside the answer |
| Separate pages for the same task (Search vs Agent) | One page, a mode switch |
| Advanced knobs (top-k, rerank) on the main path | Behind an Options disclosure |
| `alert()` / `confirm()` | Toasts and branded modals |
| Namespace selector repeated in every form | One Collection picker in the top bar |
| Color as the only signal | Color plus label or icon |

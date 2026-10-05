# Components

An inventory of the shared components in `ui/src`. Storybook is not used (Q14 in `planning/QUESTIONS.md`). This file and the Vitest tests do that job.

**Rules for every component**
- Colors, radii and motion come from tokens. No color literals.
- Focus is visible. The global focus ring is the seal color.
- Loading, empty and error states exist wherever data loads.
- A new shared component gets a row here and a test file.

Test paths are relative to `ui/src`. "Playwright" means a spec in `ui/e2e`.

## Base components (`components/ui`)
| Component | Purpose | Variants and states | Accessibility | Test |
|---|---|---|---|---|
| `Button` | Actions | `primary` (ink), `secondary`, `ghost`, `danger`. Sizes `sm`, `md`, `lg`, `icon`. Hover, press (scale 0.97), disabled. `asChild` for links | Native button. Visible focus ring. Icon buttons need an `aria-label` | `components/ui/ui.test.tsx` |
| `Card` | A bordered surface | `surface="console"` (8px) or `"workspace"` (12px). Parts: header, title, content | Plain container. Give a heading to the content | `components/ui/ui.test.tsx` |
| `Dialog` | Modal dialog on Radix | Trigger, content, title, description, close | Focus is trapped, Escape closes, focus returns to the trigger | `components/ui/ui.test.tsx` |
| `Sheet` | Slide-over panel on Radix Dialog, anchored right | Open and closed. Slides in over 250ms, or not at all with reduced motion | Same as Dialog. Needs a title and description | `features/requests/requests.test.tsx` |
| `Input`, `Textarea` | Text fields | Default, hover, focus (seal ring), disabled, invalid | Pair with a `label`. Invalid sets `aria-invalid` | `components/ui/ui.test.tsx` |
| `Select` | Native select, styled | Default, hover, focus, disabled | Native keyboard and mobile behavior. Give it an `aria-label` | No unit test. It is used in the Requests filters and exercised by their tests |
| `Segmented` | Single-select control on Radix Toggle Group | Selected and unselected. Cannot be cleared | `radiogroup` with `radio` items. Arrow keys move | `components/ui/ui.test.tsx` |
| `Skeleton` | Loading placeholder in the final shape | Shimmer. Still with reduced motion | `aria-hidden`. The parent carries `role="status"` and `aria-busy` | `components/ui/ui.test.tsx` |

## Governance components (`components/governance`)
| Component | Purpose | Variants and states | Accessibility | Test |
|---|---|---|---|---|
| `VerdictBadge` | One verdict: icon, word, color | `allow`, `deny` (plus the reason code in mono), `escalate`, `unrecorded`. Sizes `sm`, `md` | Never color alone. `data-verdict` for tests | `components/governance/governance.test.tsx` |
| `DenyCallout`, `DenyCalloutView` | Deny emphasis: failing stage in red, plain sentence, policy field and version | `DenyCallout` reads the reason catalogue. `DenyCalloutView` takes the sentence and field, for public pages with example data | A labelled region. Icon, word and color together | `components/governance/deny-callout.test.tsx` |
| `TraceTimeline` | The decisions of one request as a rail, oldest first | Denied step anchored with a red bar and the plain sentence (with `reasons`). Current step marked. Empty message | An ordered list. `aria-current="step"` on the current step | `components/governance/governance.test.tsx`, `trace-deny.test.tsx` |
| `Receipt` | The readable view of one decision | Full, or `compact` (five fields). A missing value reads "none" | A labelled region with a definition list. Each value has a copy button | `components/governance/governance.test.tsx` |
| `CopyValue` | A mono value with a copy button | Default and copied | The button says what it copies, and says when it did | `components/governance/governance.test.tsx` (through Receipt) |
| `ErrorState` | API error code and request id, with retry | With and without retry. Non-API errors fall back to `unknown_error` | `role="alert"` | `components/governance/governance.test.tsx` |
| `EmptyState` | Says what would appear and how to make it appear | With or without an action | A heading and plain text | `components/governance/governance.test.tsx` |
| `TableSkeleton` | Skeleton rows in table shape | Rows and columns | `role="status"`, `aria-busy` | `components/governance/governance.test.tsx` |
| `PageHeader` | Page title, text, actions | With or without text and actions | The one `h1` of the page | Covered by page tests |
| `Logo`, `LogoMark` | The mark and the name | Link to the home route | The link has an `aria-label` | Playwright (shell) |

## Feature components
| Component | Where | Purpose | States | Test |
|---|---|---|---|---|
| `AppShell` | `app/shell.tsx` | Sidebar, top bar, skip link, palette and session menu | Mobile menu. Mode chip | Playwright (`governance.spec.ts`, `polish.spec.ts`) |
| `SessionMenu` | `app/session-menu.tsx` | Who you are, tenant, scopes, theme, sign out | Preview shows "read-only preview" | `app/session-menu.test.tsx` |
| `CommandPalette` | `app/command-palette.tsx` | Cmd or Ctrl plus K: go to a screen or find a request id | Empty, matches, typed id | `app/command-palette.test.tsx` |
| `OverviewTiles`, `TopDenyReasons`, `ByDayBars` | `features/overview` | The four numbers, the top deny reasons, requests per day | Empty, loading and error on the page | `features/overview/overview.test.tsx` |
| `RequestsTable` | `features/requests` | One row per request | Loading, empty, filtered empty, error, selected row, density | `features/requests/requests.test.tsx` |
| `RequestDrawer`, `RequestDetailView` | `features/requests` | Slide-over with the request's verdict, deny emphasis, trace and receipts | Loading, not found, error | `features/requests/requests.test.tsx` |
| `DecisionsTable`, `DecisionDetailView` | `features/decisions` | One row per decision, and one decision's detail | As above | `components/governance/governance.test.tsx`, `trace-deny.test.tsx` |
| `GovernanceLine` | `features/ask` | "Checked by policy v3 · 2 checks · allowed", linking to the request | Loading, error, hidden without a request id | `features/ask/governance-line.test.tsx` |
| `AnswerView` | `features/ask` | The answer, verdict, confidence, governance line, evidence | Flagged, no evidence | `features/ask/ask.test.tsx` |
| Walkthrough | `features/walkthrough` | Runs one allowed and one blocked request and shows both side by side | No knowledge base, error, no passage matched | `features/walkthrough/walkthrough.test.tsx` |
| `SignInForm` | `features/auth` | API key sign-in, and the read-only preview button | Pending, error with code | `features/auth/signin-form.test.tsx` |
| `DayChart` | `features/usage` | Requests per day on the Usage page | A hidden table with the same numbers | Playwright (`governance.spec.ts`) |

## Landing components (`landing`)
These are the only components that may load GSAP or three.js.
| Component | Purpose | States | Test |
|---|---|---|---|
| `LandingPage`, `HowItWorksPage` | The two public pages | Reduced motion: no animation | Playwright (`landing.spec.ts`, `a11y.spec.ts`) |
| `ReceiptVerifier`, `VerificationResult` | Trust page: decision id (or pasted receipt) to a valid or invalid result with each check, chain position and key id | Idle, checking, valid, invalid, API error. Result is icon, word and color together | Vitest (`trust.test.tsx`), Playwright (`trust.spec.ts`, with axe) |
| `RetentionCard`, `EvalGateCard` | Trust page: retention settings (read only) and the eval gate latest run and history | Default or tenant retention, no purge yet, no eval run, passed, failed | Vitest (`trust.test.tsx`) |
| `MarketingShell` | Header and footer for both pages | Narrow screens hide secondary links | Playwright (`responsive.spec.ts`) |
| `HeroVisual` | The quiet ring behind the hero, with a static poster | `off`, `loading`, `ready`. Paused off-screen | Playwright (`landing.spec.ts`) |
| `ScrollStory` | The pinned scroll story of one request | Pinned, or a plain list with reduced motion and on narrow screens | Playwright (`landing.spec.ts`) |
| `StoryPanel` | The five story panels, built from the real components with example data | Labelled "Example" | Playwright (`landing.spec.ts`) |

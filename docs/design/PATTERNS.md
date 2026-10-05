# Governance patterns

These patterns are specific to this product. They always apply. The code is in `ui/src/components/governance` unless stated.

## Verdict
Each verdict has a token, an icon and a word. Color is never the only signal.

| Verdict | Token | Icon | Word |
|---|---|---|---|
| Allow | `allow` | check circle | Allowed |
| Deny | `deny` | prohibit | Denied, plus the reason code in mono |
| Escalate | `escalate` | hand | Needs approval (designed, not built) |
| Not recorded | `warning` | warning circle | Not recorded |

Component: `VerdictBadge`. A request is a deny when any of its decisions was a deny. Otherwise it is an allow.

## Trace
A vertical rail of the decisions in one request, oldest first. Each step shows the action and resource in mono, the verdict, the stage, a timestamp and the time to the next step. The denied step is the anchor of a denied trace: a red bar, the stage in red, and the plain sentence. Steps open in place, never in a modal. Component: `TraceTimeline`.

## Receipt
The readable view of one decision, in mono: decision id, request id, policy version, tenant, principal, action, resource, stage, reason, input SHA-256 and time. Each value can be copied. A missing value reads "none". The input text is never shown, because the platform does not store it. Component: `Receipt`.

## Deny emphasis
Deny is the loudest state on any screen. A denied call shows four things together:
1. **The failing stage**, in red, named in plain words ("Denied at Tenant policy") with the stage code in mono. The stage comes from the decision row.
2. **One plain sentence** from the reason catalogue.
3. **The policy field** behind the stop in mono, for example `allowed_kbs`. When no policy key is behind it, it says "none".
4. **The policy version** that applied, or "platform default".

Component: `DenyCallout`. It is used in Ask, the request drawer, the decision detail and the walkthrough. A denial is not an error. It has its own panel and never uses the error state.

`query_blocked` is also raised by the built-in injection patterns. It names `blocked_terms` as the policy field only when the tenant policy holds blocked terms.

## Governance line
A single line under each answer in Ask, for example "Checked by policy v3 · 2 checks · allowed". It links to the request, which opens in the drawer. A request with no tenant policy reads "Checked by the platform default policy". The line reads the request id from the `X-Request-ID` header, then fetches `/v1/requests/{id}`. A denied ask shows it too. Component: `GovernanceLine`.

## Request drawer
A slide-over on Radix Dialog at `/app/requests/:requestId`. It shows the verdict, the deny emphasis, the stage trace, the request details (id, start, principal, tenant) and one receipt link per decision. It opens from the Requests table, the governance line, the walkthrough, the palette and a decision's "Open the whole request" link. Escape or the close button returns to the list with its filters. A request id that is not found says so. Component: `RequestDrawer`.

## Overview numbers
Four numbers: checked, blocked, deny rate and budget used. They count requests, not decision rows, so they match the Requests table. Each links to `/app/requests` with the matching filter. Console views, such as the Overview itself, are left out by default. Requests has an "Include console views" switch, off by default.

## Walkthrough
The first run. It sends one normal question and one question that the input guardrails stop, against the first knowledge base the session can read. It shows both results side by side, each with its verdict, stage trace, plain reason and a link to the request. Every tenant has the input guardrails, so it works without setup. If the session has no knowledge base it says why and links to the Library. If the normal question finds no matching passage, it says so and still shows the allow decision.

## Secrets
Key screens show the prefix, scopes, created time and last-used time only. A secret appears once, in a copy-once dialog, and is never fetched again.

## Browser storage
The UI keeps a few per-browser conveniences in `localStorage`. This is the full list of allowed keys. Each holds a preference or a non-secret slug, every read and write is wrapped in try/catch, and the page works with storage blocked. A new key needs an entry here.

| Key | Holds |
|---|---|
| `theme` | The chosen theme: light, dark or auto. |
| `density` | The row density: compact or comfortable. |
| `walkthrough-seen` | `1` once the walkthrough has opened, so later sign-ins open the Overview. |
| `ask-history` | This browser's list of asks: question, knowledge base, request id and verdict. No answers and no credentials. |
| `collection` | The last knowledge base picked in the Library. A knowledge-base slug, not a secret. |

Never store an API key, a session token, a CSRF token or document text in browser storage.

## Empty, loading and error states
Every screen has all three.
- **Loading:** skeletons in the final layout shape. Never a centered spinner on a table.
- **Empty:** say what would appear here and how to make it appear. A filtered empty state points at the filters.
- **Error:** the API error `code` and `request_id` in mono, a plain message and a "Try again" button.
- **Read-only session:** actions the session cannot do are disabled, and the page says why.

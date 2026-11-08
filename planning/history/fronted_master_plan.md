# AI Platform — Frontend Master Implementation Plan
## Single Authoritative Document. All Previous Drafts Superseded.

> **Verified against:** live source at `/home/ubuntu/ai-platform/`
> **Verification date:** 2026-08-10
> **Backend version:** `0.4.0`
> **Routes verified:** `api/routers/{health,search,ingest,config,analytics,docs,feedback}.py`, `api/agent/router.py`, `api/mcp/transport.py`, `api/middleware/{finops,logging,rate_limit,token_budget}.py`, `api/models/schemas.py`, `config.py`
> **All previous drafts are superseded by this document. Do not reference them.**

---

## Validated Correction Log (from previous drafts)

| Error in earlier drafts | Correct value (source-verified) |
|---|---|
| `/agent/query` listed as Phase 2 (non-existent) | **Live** in `api/agent/router.py` — Phase 1 |
| `/mcp/sse` listed as Phase 2 | **Live** in `api/mcp/transport.py` |
| `ingest.js` imports `BASE_URL` from `./client` | `client.js` does NOT export `BASE_URL`. Use `import.meta.env` directly. |
| Field: `throughput_chunks_per_sec` | Actual: **`throughput_chunks_per_second`** |
| Field: `ingested_at` (documents) | Actual: **`last_ingested_at`** |
| Sidebar hardcoded `v0.2.0` | Read from `health.version` at runtime |
| `NAMESPACE_REGISTRY` = `{key: {label, description}}` | Actual shape: **`{key: "description string"}`** — flat map |
| Health fetched in TopBar AND App separately | Lifted to `App.jsx`, passed as prop — fetched once |
| `POST /feedback` returns HTTP 200 | Returns **HTTP 201** (`status_code=201`) |
| Analytics response has no `days` field | Response includes `"days": N` at root |
| Analytics response has no `total_tokens` | Response includes `"total_tokens"` at root and `"tokens"` per `by_day` entry |
| No `rerank_applied` on SearchResponse | **Exists** in `api/models/schemas.py` line 49, set from `effective_rerank` |

---

## Part 1: All Live Backend Routes

### Phase 1 — Build UI for these now

| Route | Method | Status |
|---|---|---|
| `/health` | GET | ✅ Live |
| `/config` | GET | ✅ Live — `api/routers/config.py` |
| `/search` | POST JSON | ✅ Live |
| `/ingest` | POST multipart | ✅ Live |
| `/agent/query` | POST JSON | ✅ Live — `api/agent/router.py` |
| `/documents` | GET | ✅ Live — `api/routers/docs.py` |
| `/analytics/summary` | GET `?days=N` | ✅ Live — `api/routers/analytics.py` |
| `/feedback` | POST JSON | ✅ Live — returns 201 |
| `/quality-report` | GET `?days=N` | ✅ Live |

### Not called by browser directly

| Route | Why |
|---|---|
| `/mcp/sse` | MCP SSE stream — displayed as static info only |
| `/mcp/messages` | ASGI raw mount — not a REST endpoint |

### Phase 2 — Needs future backend work

| Route | Needed for |
|---|---|
| None currently | All planned features are now live |

---

## Part 1b: UI Structure

### Shell Layout

Every page shares a persistent outer shell. The shell never re-mounts — only the `<main>` content region changes as the user navigates.

```
┌────────────────────────────────────────────────────────────┐
│  TopBar                                               52px  │
│  [● status dot] [AI Platform]          [mode] [↑ uptime]  │
├───────────┬────────────────────────────────────────────────┤
│           │                                                │
│  Sidebar  │  <main>  (scrollable, page content renders)   │
│  220px    │                                                │
│           │                                                │
│  [◈] Dashboard                                            │
│  [⌕] Search                                               │
│  [⟳] Agent                                                │
│  [⇑] Ingest                                               │
│  [▲] Analytics                                            │
│  [▤] Documents                                            │
│           │                                                │
│  ─────────│                                                │
│  v0.4.0   │                                                │
└───────────┴────────────────────────────────────────────────┘
```

- **TopBar** (`height: 52px`): Platform name, live health indicator (pulsing dot), mode badge (LOCAL/DEMO/PROD), formatted uptime, version string.
- **Sidebar** (`width: 220px`): Logo lockup + nav links. Active link styled with amber accent background + amber text. Version shown at bottom. Never collapses.
- **Main** (`flex: 1`, scrollable): Page-specific content. Has `contain: layout style` for isolation.

---

### Page: Dashboard (`/`)

Purpose: At-a-glance health and platform info. No forms, no input. Informational only.

```
/
├── [h1] Dashboard
├── Section: System Health
│   └── [card] DB  [card] Redis  [card] API
│          status dot + "Operational" | "Error"
│
└── Section: Platform Info
    ├── [card] Mode badge (LOCAL / DEMO / PROD)
    ├── [card] Uptime (e.g. "4h 32m")
    ├── [card] Version (e.g. "0.4.0")
    └── [card] Overall status badge

+ Retrieval Mode explanation table (for tooltip context)
```

Data source: `health` prop passed from `App.jsx`. No additional fetch on this page.

---

### Page: Search (`/search`)

Purpose: Single-shot RAG query. The core functional page.

```
/search
├── [h1] Search
│
├── SearchForm
│   ├── [textarea] Query input (Ctrl+Enter to submit)
│   ├── [button] Search
│   ├── [select] Namespace (populated from config.namespaces)
│   ├── [radio group] Retrieval mode (Hybrid | Vector | BM25)
│   ├── [range] Top-K slider (1-20)
│   └── [toggle] Rerank (disabled if config.reranker_enabled = false)
│
└── Results (after submit, aria-live="polite")
    ├── [banner] GuardrailBanner — if blocked (400) | flagged | clarification needed
    ├── [card accent] AnswerBlock (markdown rendered)
    │   └── FeedbackButtons (👍 👎, uses X-Query-ID)
    ├── [row]
    │   ├── [card] ConfidenceGauge (0-100%, with config.confidence_floor threshold)
    │   └── [card] MetaBar (cache badge, cost, tokens in/out, time, budget, request ID)
    └── [section] Citations
        └── [card × N] CitationCard (doc, namespace, score badge, expandable excerpt)
```

---

### Page: Agent (`/agent`)

Purpose: Multi-step reasoning with full observability into the agent's work.

```
/agent
├── [h1] Agent
│
├── AgentForm
│   ├── [textarea] Question input
│   ├── [select] Namespace
│   ├── [range] Max iterations slider (1-10)
│   ├── [toggle] Enable verifier
│   └── [range] Verify retries slider (0-3) — shown only if verifier is on
│
└── Results (after submit, aria-live="polite")
    ├── [card accent] AnswerBlock (markdown rendered)
    │   └── FeedbackButtons (👍 👎, uses X-Query-ID)
    ├── [row]
    │   ├── [card] ConfidenceGauge
    │   ├── [card] VerificationBadge (Verified ✓ / Unverified ✗ / Not Run)
    │   └── [card] MetaBar + Agent Stats (tool_calls_made, total_time, cost, model)
    ├── [collapsible] ReasoningChain
    │   └── [ol] Tool call steps (⚙ icon) + Tool result steps (↩ icon)
    └── [section] Citations
        └── [card × N] AgentCitationCard (source_filename, chunk_index, relevance score, excerpt)
```

---

### Page: Ingest (`/ingest`)

Purpose: Upload documents to a namespace.

```
/ingest
├── [h1] Ingest Documents
│
├── DropZone (drag-and-drop OR click to browse)
│   ├── accepts: .txt, .md, .pdf
│   └── shows: filename + filesize after selection, with clear (✕) button
│
├── Options
│   ├── [select] Namespace
│   └── [input] Document ID (optional, defaults to filename)
│
├── [button] Ingest Document (disabled until file selected)
│
├── [banner] Error (415 unsupported type | 429 rate limit)
│
└── IngestResult (shown after success)
    ├── Status badge: New Document / Updated / Unchanged
    ├── Description text
    └── Metrics grid: document_id, namespace, chunks_created,
        chunks_deleted (if > 0), time, throughput, SHA-256 hash
```

---

### Page: Analytics (`/analytics`)

Purpose: Cost and usage visibility. No forms — purely observational.

```
/analytics
├── [h1] Analytics
│   └── Day picker: [7d] [14d] [30d] [90d] (aria-pressed)
│
├── Summary Row (4 cards)
│   ├── [card] Total cost
│   ├── [card] Total requests
│   ├── [card] Avg cost / request
│   └── [card] Total tokens
│
├── Breakdown Grid (3 cards)
│   ├── [card] By namespace (list: namespace → cost + requests)
│   ├── [card] By endpoint (list: /search → cost + requests)
│   └── [card] By model (list: model short name → cost + requests)
│
└── [card] Daily breakdown table
    └── columns: Date | Cost | Tokens | Requests
```

Data source: `GET /analytics/summary?days={N}`. Re-fetches when day picker changes.

---

### Page: Documents (`/documents`)

Purpose: Registry of all ingested documents with chunk counts and timestamps.

```
/documents
├── [h1] Documents
│   └── [select] Namespace filter (All / legal / kyc_aml / default)
│
└── [card] Document table
    └── columns: Document | Namespace | Chunks | SHA-256 | Last Ingested
    └── [empty state] "No documents ingested in this namespace."
```

Data source: `GET /documents?namespace={ns}`. Re-fetches when namespace filter changes.
`last_ingested_at` rendered with `new Date(doc.last_ingested_at).toLocaleString()`.

---

### Information Hierarchy Summary

| Page | Primary data | Secondary data | Tertiary |
|---|---|---|---|
| Dashboard | Health status | Mode, uptime, version | Retrieval mode guide |
| Search | Answer | Confidence, cache, cost | Citations, request ID |
| Agent | Answer | Verification, reasoning | Citations, model, timing |
| Ingest | Upload result | Chunk count, throughput | SHA-256, chunks_deleted |
| Analytics | Total cost | By-day breakdown | By model, by endpoint |
| Documents | Document list | Chunk counts | Content hash |

---

## Part 2: Response Headers (Verified against middleware source)

These headers appear on `/search` and `/agent/query` responses. Both `X-Budget-*` headers only appear when tokens were actually used (i.e., cache miss path).

```
X-Request-ID          → uuid4().hex            RequestIDMiddleware
X-Process-Time        → "14.52ms"              LatencyMiddleware
X-Cost-USD            → "0.000186"             FinOpsMiddleware
X-Tokens-In           → "847"                  FinOpsMiddleware
X-Tokens-Out          → "312"                  FinOpsMiddleware
X-Query-ID            → same value as X-Request-ID  FinOpsMiddleware (reads request.state.request_id)
X-Budget-Remaining    → "483000"               TokenBudgetMiddleware (post-response, on usage)
X-Budget-Limit        → "500000"               TokenBudgetMiddleware
X-RateLimit-Limit     → "60"                   RateLimitMiddleware
X-RateLimit-Remaining → "57"                   RateLimitMiddleware
X-Cache               → "HIT" | "MISS"          Search route only
X-Cache-Type          → "exact"|"semantic"|"none"  Search route only
```

`/ingest` also now stamps `X-Query-ID` (fixed in backend iteration).

For `expose_headers` in CORS — all of the above must be listed.

---

## Part 3: All Response Shapes (Source-Verified)

### `GET /health`

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "version": "0.4.0",
  "mode": "local",
  "uptime_seconds": 3612
}
```

### `GET /config`

```json
{
  "namespaces": {
    "legal":   "GDPR, CCPA, HIPAA, and other data protection regulations",
    "kyc_aml": "KYC, AML, and Bank Secrecy Act documentation",
    "default": "Uncategorized or general compliance documents"
  },
  "confidence_floor": 0.45,
  "max_query_length": 1000,
  "daily_token_budget": 500000,
  "rate_limit_rpm": 60,
  "rate_limit_window_seconds": 60,
  "reranker_enabled": true,
  "agent_defaults": {
    "max_iterations": 6,
    "enable_verifier": true,
    "max_verify_retries": 1
  }
}
```

> **`namespaces` is a flat `{key: description}` map.** Not `{key: {label, description}}`. To get namespace keys: `Object.keys(config.namespaces)`. To get description: `config.namespaces[key]`.

### `POST /search`

```json
{
  "query": "What are GDPR breach notification requirements?",
  "answer": "Under GDPR Article 33...",
  "confidence": 0.91,
  "needs_clarification": false,
  "results": [
    {
      "document_id": "gdpr.pdf",
      "namespace": "legal",
      "content": "Article 33: In the case of a personal data breach...",
      "score": 0.8741,
      "metadata": { "chunk_index": 17 }
    }
  ],
  "total_results": 5,
  "flagged": false,
  "flag_reason": null,
  "rerank_applied": true
}
```

> `rerank_applied` = what the backend actually did (may differ from what the client requested if in demo mode).

### `POST /agent/query`

```json
{
  "question": "Compare GDPR and CCPA breach notification timelines",
  "answer": "GDPR Article 33 requires notification within 72 hours...",
  "confidence": 0.88,
  "citations": [
    {
      "document_id": "gdpr.pdf",
      "source_filename": "gdpr.pdf",
      "chunk_index": 42,
      "relevance_score": 0.923,
      "excerpt": "Article 33: notification shall be made within 72 hours..."
    }
  ],
  "model_used": "groq/meta-llama/llama-4-scout-17b-16e-instruct",
  "verified": true,
  "verification_notes": "Answer accurately reflects retrieved content.",
  "reasoning_steps": [
    "Called tool: retrieve_chunks({'query': 'GDPR breach', 'namespace': 'legal'})",
    "Tool result: Article 33 within 72 hours...",
    "Called tool: retrieve_chunks({'query': 'CCPA breach timeline', 'namespace': 'legal'})",
    "Tool result: Expedient notification required..."
  ],
  "tool_calls_made": 2,
  "total_time_seconds": 8.34,
  "total_cost_usd": 0.000412
}
```

> `verified`: `true | false | null`. `null` = verifier was disabled (`enable_verifier: false`).

### `POST /ingest` (multipart)

```json
{
  "document_id": "gdpr.pdf",
  "namespace": "legal",
  "total_chunks": 142,
  "total_time_seconds": 4.82,
  "throughput_chunks_per_second": 29.46,
  "status": "new",
  "content_hash": "a1b2c3d4...",
  "chunks_deleted": 0
}
```

> `status`: `"new" | "updated" | "unchanged"`. When `"unchanged"`, `total_chunks = 0`.

### `GET /analytics/summary?days=7`

```json
{
  "days": 7,
  "total_cost_usd": 0.0412,
  "total_requests": 148,
  "total_tokens": 84200,
  "avg_cost_per_request": 0.000278,
  "by_day": [
    { "date": "2026-08-07", "cost_usd": 0.0082, "tokens": 6100, "requests": 24 }
  ],
  "by_endpoint": [
    { "endpoint": "/search", "cost_usd": 0.031, "requests": 112 }
  ],
  "by_namespace": [
    { "namespace": "legal", "cost_usd": 0.031, "requests": 112 }
  ],
  "by_model": [
    { "model": "groq/meta-llama/llama-4-scout-17b-16e-instruct", "cost_usd": 0.041, "requests": 148 }
  ]
}
```

> `by_day[].date` is a plain `"YYYY-MM-DD"` string. `new Date("2026-08-07")` parses correctly.

### `GET /documents?namespace=legal`

```json
{
  "documents": [
    {
      "document_id": "gdpr.pdf",
      "namespace": "legal",
      "source_filename": "gdpr.pdf",
      "content_hash": "a1b2c3d4...",
      "chunk_count": 142,
      "last_ingested_at": "2026-08-01T14:22:00+00:00"
    }
  ],
  "count": 1
}
```

> Field is `last_ingested_at` (NOT `ingested_at`). Serialized via `.isoformat()` — `new Date(doc.last_ingested_at)` works correctly.

### `POST /feedback` → HTTP 201

```json
// Request body
{ "request_id": "a3f9b2c1hex...", "endpoint": "/search", "rating": "up", "comment": null }

// Response (201)
{ "status": "recorded" }
```

> `request_id` = the `X-Query-ID` header value from the original `/search` or `/agent/query` response.

### `GET /quality-report?days=30`

```json
{
  "days": 30,
  "by_endpoint": [
    {
      "endpoint": "/search",
      "thumbs_up": 42,
      "thumbs_down": 5,
      "total": 47,
      "approval_rate": 0.894
    }
  ]
}
```

> `approval_rate` is `null` when `total = 0` (pre-computed server-side).

### Error shapes

```json
// 400 — query blocked by input guardrail
{ "detail": { "error": "query_blocked", "reason": "..." } }

// 404 — no documents in namespace
{ "detail": "No documents found in namespace 'legal'..." }

// 415 — unsupported file type (ingest)
{ "detail": "Unsupported file type: .docx" }

// 429 — rate limit exceeded
{ "error": "rate_limit_exceeded", "namespace": "legal", "limit": 60, "window_seconds": 60, "retry_after_seconds": 42 }

// 429 — daily token budget exceeded (different body shape than rate limit)
{ "error": "daily_token_budget_exceeded", "namespace": "legal", "tokens_used": 500100, "daily_limit": 500000, "resets_at": "2026-08-10T00:00:00Z (next UTC midnight)" }

// 500 — agent execution failed
{ "detail": "Agent execution failed: <reason>" }

// 500 — feedback insert failed
{ "detail": "Failed to record feedback: <reason>" }
```

---

## Part 4: Backend Change Required Before Building

Only one change is needed: add `CORSMiddleware` to `api/main.py`. This does not exist yet. Without it no browser `fetch()` call from any origin will work.

```python
# Add this import at the top of api/main.py
from fastapi.middleware.cors import CORSMiddleware

# Add this LAST in the add_middleware block (LIFO — last added = first executed)
# Must run before all other middleware to handle CORS preflight OPTIONS requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:4173",    # Vite preview
        "http://localhost:3000",    # Alternative dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Cost-USD",
        "X-Tokens-In",
        "X-Tokens-Out",
        "X-Query-ID",
        "X-Request-ID",
        "X-Process-Time",
        "X-Cache",
        "X-Cache-Type",
        "X-Budget-Remaining",
        "X-Budget-Limit",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
    ],
)
```

The final middleware order in `main.py` (LIFO — last added runs first):

```
CORSMiddleware        ← add last (runs first — handles preflight before anything else)
RateLimitMiddleware
RequestIDMiddleware
TokenBudgetMiddleware
FinOpsMiddleware
LatencyMiddleware
LoggingMiddleware     ← add first (runs last — innermost)
```

---

## Part 5: Design System

```css
/* src/index.css */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  /* ── Tier 1: Core primitives ── */
  --gray-1000: #080a10;  --gray-950: #0c0e16;   --gray-900: #151821;
  --gray-850:  #1a1e2c;  --gray-800: #1d2130;   --gray-750: #242840;
  --gray-700:  #2d3250;  --gray-600: #3d4466;   --gray-500: #5a6280;
  --gray-400:  #8892a4;  --gray-300: #b0bac8;   --gray-200: #d4dae6;

  --amber-700: #b45309;  --amber-600: #d97706;  --amber-500: #e8a020;
  --amber-400: #fbbf24;  --amber-300: #fcd34d;  --amber-200: #fde68a;

  --cyan-600:  #0891b2;  --cyan-500:  #06b6d4;  --cyan-400: #22d3ee;
  --cyan-300:  #67e8f9;

  --emerald-600: #059669; --emerald-500: #10b981; --emerald-400: #34d399;
  --red-600:   #dc2626;  --red-500:   #ef4444;  --red-400:   #f87171;
  --yellow-500: #eab308; --yellow-400: #facc15;

  /* ── Tier 2: Semantic tokens ── */
  --bg-base:        var(--gray-950);
  --bg-surface:     var(--gray-900);
  --bg-elevated:    var(--gray-800);
  --bg-sunken:      var(--gray-1000);
  --bg-overlay:     rgba(8, 10, 16, 0.7);

  --border-subtle:  var(--gray-850);
  --border-default: var(--gray-750);
  --border-strong:  var(--gray-700);
  --border-accent:  rgba(232, 160, 32, 0.35);

  --text-primary:   #f0f2f8;
  --text-secondary: var(--gray-300);
  --text-muted:     var(--gray-400);
  --text-disabled:  var(--gray-600);
  --text-inverse:   var(--gray-950);

  --accent:         var(--amber-500);
  --accent-dim:     var(--amber-600);
  --accent-subtle:  rgba(232, 160, 32, 0.10);
  --accent-glow:    rgba(232, 160, 32, 0.20);

  --data:           var(--cyan-400);
  --data-dim:       var(--cyan-500);
  --data-subtle:    rgba(34, 211, 238, 0.08);

  --success:        var(--emerald-500);
  --success-subtle: rgba(16, 185, 129, 0.10);
  --warning:        var(--yellow-400);
  --warning-subtle: rgba(234, 179, 8, 0.10);
  --danger:         var(--red-500);
  --danger-subtle:  rgba(239, 68, 68, 0.10);

  /* ── Tier 3: Component tokens ── */
  --btn-primary-bg:    var(--accent);
  --btn-primary-text:  var(--text-inverse);
  --btn-primary-hover: var(--accent-dim);
  --btn-ghost-hover:   var(--bg-elevated);
  --input-bg:          var(--bg-sunken);
  --input-border:      var(--border-default);
  --input-border-focus:var(--accent);
  --input-text:        var(--text-primary);
  --input-placeholder: var(--text-muted);
  --card-bg:           var(--bg-surface);
  --card-border:       var(--border-default);
  --card-hover-border: var(--border-strong);
  --badge-hit-bg:      rgba(16,185,129,0.12);
  --badge-hit-text:    var(--emerald-400);
  --badge-miss-bg:     rgba(90,98,128,0.20);
  --badge-miss-text:   var(--gray-300);

  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  --space-1:4px; --space-2:8px;  --space-3:12px; --space-4:16px;
  --space-5:20px;--space-6:24px; --space-8:32px; --space-10:40px;
  --space-12:48px; --space-16:64px;

  --radius-sm:6px;  --radius-md:10px; --radius-lg:14px;
  --radius-xl:20px; --radius-full:9999px;

  --transition-fast:150ms ease; --transition-normal:200ms ease; --transition-slow:300ms ease;

  --shadow-sm:  0 1px 3px rgba(8,10,16,0.4);
  --shadow-md:  0 4px 12px rgba(8,10,16,0.5);
  --shadow-lg:  0 8px 24px rgba(8,10,16,0.6);
  --shadow-accent: 0 0 20px rgba(232,160,32,0.15);
}

*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
html { font-size:16px; -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }
body { font-family:var(--font-sans); background:var(--bg-base); color:var(--text-primary); line-height:1.6; min-height:100vh; overflow-x:hidden; }

::-webkit-scrollbar { width:6px; height:6px; }
::-webkit-scrollbar-track { background:var(--bg-base); }
::-webkit-scrollbar-thumb { background:var(--gray-700); border-radius:var(--radius-full); }

:focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:var(--radius-sm); }
a,button,input,select,textarea { transition:var(--transition-normal); }

h1 { font-size:1.75rem; font-weight:700; line-height:1.2; letter-spacing:-0.025em; }
h2 { font-size:1.375rem; font-weight:600; line-height:1.3; letter-spacing:-0.02em; }
h3 { font-size:1.125rem; font-weight:600; line-height:1.4; }
p  { font-size:0.9375rem; line-height:1.65; color:var(--text-secondary); }
code,pre { font-family:var(--font-mono); font-size:0.875em; }

.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }

@keyframes shimmer { 0%{background-position:-200% 0} 100%{background-position:200% 0} }
.skeleton { background:linear-gradient(90deg,var(--bg-surface) 25%,var(--bg-elevated) 50%,var(--bg-surface) 75%); background-size:200% 100%; animation:shimmer 1.5s infinite; border-radius:var(--radius-sm); }

@keyframes pulse-dot { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(0.85)} }
@keyframes fadeIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
.fade-in { animation:fadeIn 200ms ease forwards; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
.cursor::after { content:'▋'; display:inline-block; color:var(--accent); animation:blink 1s step-end infinite; margin-left:1px; }
@keyframes spin { to{transform:rotate(360deg)} }
@keyframes loadSlide { to{left:150%} }
```

---

## Part 6: File Structure

```
ui/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx
    ├── App.jsx                     ← health + config state lifted here
    ├── index.css
    ├── api/
    │   ├── client.js               ← apiFetch wrapper (only export)
    │   ├── health.js               ← GET /health
    │   ├── config.js               ← GET /config
    │   ├── search.js               ← POST /search
    │   ├── agent.js                ← POST /agent/query
    │   ├── ingest.js               ← POST /ingest (multipart — does NOT use client.js)
    │   ├── analytics.js            ← GET /analytics/summary
    │   ├── documents.js            ← GET /documents
    │   └── feedback.js             ← POST /feedback, GET /quality-report
    ├── components/
    │   ├── layout/
    │   │   ├── Layout.jsx + .module.css
    │   │   ├── Sidebar.jsx + .module.css
    │   │   └── TopBar.jsx + .module.css
    │   ├── ui/
    │   │   ├── Badge.jsx + .module.css
    │   │   ├── Button.jsx + .module.css
    │   │   ├── Card.jsx + .module.css
    │   │   ├── StatusDot.jsx + .module.css
    │   │   └── Toggle.jsx + .module.css
    │   ├── search/
    │   │   ├── SearchForm.jsx + .module.css
    │   │   ├── AnswerBlock.jsx + .module.css
    │   │   ├── CitationCard.jsx + .module.css
    │   │   ├── ConfidenceGauge.jsx + .module.css
    │   │   ├── MetaBar.jsx + .module.css
    │   │   └── GuardrailBanner.jsx + .module.css
    │   ├── agent/
    │   │   ├── AgentForm.jsx + .module.css
    │   │   ├── ReasoningChain.jsx + .module.css
    │   │   ├── VerificationBadge.jsx + .module.css
    │   │   └── AgentCitationCard.jsx + .module.css
    │   ├── ingest/
    │   │   ├── DropZone.jsx + .module.css
    │   │   └── IngestResult.jsx + .module.css
    │   └── feedback/
    │       └── FeedbackButtons.jsx + .module.css
    └── pages/
        ├── Dashboard.jsx + .module.css
        ├── Search.jsx + .module.css
        ├── Agent.jsx + .module.css
        ├── Ingest.jsx + .module.css
        ├── Analytics.jsx + .module.css
        └── Documents.jsx + .module.css
```

---

## Part 7: `package.json` and `vite.config.js`

```json
{
  "name": "ai-platform-ui",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build", "preview": "vite preview" },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.1",
    "react-markdown": "^9.0.1",
    "remark-gfm": "^4.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.0"
  }
}
```

```js
// vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
  build: { outDir: 'dist', rollupOptions: { output: { manualChunks: undefined } } },
})
```

---

## Part 8: `index.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="AI Platform — compliance document retrieval with hybrid RAG, LangGraph agent reasoning, FinOps cost tracking, and MCP integration." />
  <meta name="theme-color" content="#0c0e16" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <title>AI Platform</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
```

---

## Part 9: `src/main.jsx`

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
```

---

## Part 10: `src/App.jsx`

`health` and `config` are both fetched here and passed as props. Neither is fetched again anywhere else.

```jsx
import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Search from './pages/Search'
import Agent from './pages/Agent'
import Ingest from './pages/Ingest'
import Analytics from './pages/Analytics'
import Documents from './pages/Documents'
import { getHealth } from './api/health'
import { getConfig } from './api/config'

export default function App() {
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)

  // Health: poll every 30s — connectivity and uptime change
  useEffect(() => {
    async function check() {
      try { setHealth(await getHealth()) } catch { setHealth(null) }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  // Config: fetch once — static for the session
  useEffect(() => {
    getConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  return (
    <Routes>
      <Route element={<Layout health={health} />}>
        <Route index element={<Dashboard health={health} />} />
        <Route path="search"    element={<Search config={config} />} />
        <Route path="agent"     element={<Agent config={config} />} />
        <Route path="ingest"    element={<Ingest config={config} />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="documents" element={<Documents config={config} />} />
        <Route path="*"         element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
```

---

## Part 11: API Layer

### `src/api/client.js`

```js
const BASE = import.meta.env.VITE_API_URL ?? '/api'

// NOTE: BASE is NOT exported. Modules that can't use this wrapper
// (e.g., ingest.js which uses multipart) use import.meta.env directly.
export async function apiFetch(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const headers = extractHeaders(response.headers)
  if (!response.ok) {
    let errorBody
    try { errorBody = await response.json() }
    catch { errorBody = { detail: `HTTP ${response.status}` } }
    const error = new Error(
      errorBody.detail?.reason || errorBody.detail || errorBody.error || 'Request failed'
    )
    error.status = response.status
    error.body = errorBody
    error.headers = headers
    throw error
  }
  return { data: await response.json(), headers }
}

function extractHeaders(h) {
  return {
    costUsd:         h.get('X-Cost-USD'),
    tokensIn:        h.get('X-Tokens-In'),
    tokensOut:       h.get('X-Tokens-Out'),
    queryId:         h.get('X-Query-ID'),
    requestId:       h.get('X-Request-ID'),
    processTime:     h.get('X-Process-Time'),
    cache:           h.get('X-Cache'),
    cacheType:       h.get('X-Cache-Type'),
    budgetRemaining: h.get('X-Budget-Remaining'),
    budgetLimit:     h.get('X-Budget-Limit'),
    rateLimitLimit:  h.get('X-RateLimit-Limit'),
    rateLimitRemain: h.get('X-RateLimit-Remaining'),
  }
}
```

### `src/api/health.js`

```js
import { apiFetch } from './client'
export async function getHealth() {
  const { data } = await apiFetch('/health', { method: 'GET' })
  return data  // { status, db, redis, version, mode, uptime_seconds }
}
```

### `src/api/config.js`

```js
import { apiFetch } from './client'
export async function getConfig() {
  const { data } = await apiFetch('/config', { method: 'GET' })
  return data
  // {
  //   namespaces: { "legal": "description...", "kyc_aml": "...", "default": "..." },
  //   confidence_floor: 0.45,
  //   max_query_length: 1000,
  //   daily_token_budget: 500000,
  //   rate_limit_rpm: 60,
  //   rate_limit_window_seconds: 60,
  //   reranker_enabled: true,
  //   agent_defaults: { max_iterations: 6, enable_verifier: true, max_verify_retries: 1 }
  // }
}
```

### `src/api/search.js`

```js
import { apiFetch } from './client'
export async function search({ query, namespace = 'legal', topK = 5, retrievalMode = 'hybrid', rerank = true }) {
  return apiFetch('/search', {
    method: 'POST',
    body: JSON.stringify({ query, namespace, top_k: topK, retrieval_mode: retrievalMode, rerank }),
  })
  // Returns: { data: SearchResponse, headers }
}
```

### `src/api/agent.js`

```js
import { apiFetch } from './client'
export async function agentQuery({ question, namespace = 'default', maxIterations = 6, enableVerifier = true, maxVerifyRetries = 1 }) {
  return apiFetch('/agent/query', {
    method: 'POST',
    body: JSON.stringify({
      question,
      namespace,
      max_iterations: maxIterations,
      enable_verifier: enableVerifier,
      max_verify_retries: maxVerifyRetries,
    }),
  })
  // Returns: { data: AgentResponse, headers }
}
```

### `src/api/ingest.js`

```js
// Does NOT use apiFetch — multipart requires browser to set Content-Type boundary.
// Does NOT import from client.js — BASE_URL is not exported there.
export async function ingestFile({ file, namespace = 'legal', documentId }) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('namespace', namespace)
  if (documentId) formData.append('document_id', documentId)

  const base = import.meta.env.VITE_API_URL ?? '/api'
  const response = await fetch(`${base}/ingest`, { method: 'POST', body: formData })

  if (!response.ok) {
    let body
    try { body = await response.json() } catch { body = { detail: `HTTP ${response.status}` } }
    const err = new Error(body.detail || 'Ingest failed')
    err.status = response.status
    err.body = body
    throw err
  }
  return response.json()
  // { document_id, namespace, total_chunks, total_time_seconds,
  //   throughput_chunks_per_second, status, content_hash, chunks_deleted }
}
```

### `src/api/analytics.js`

```js
import { apiFetch } from './client'
export async function getAnalyticsSummary(days = 7) {
  const { data } = await apiFetch(`/analytics/summary?days=${days}`, { method: 'GET' })
  return data
}
```

### `src/api/documents.js`

```js
import { apiFetch } from './client'
export async function listDocuments(namespace) {
  const qs = namespace ? `?namespace=${encodeURIComponent(namespace)}` : ''
  const { data } = await apiFetch(`/documents${qs}`, { method: 'GET' })
  return data  // { documents: [...], count: N }
}
```

### `src/api/feedback.js`

```js
import { apiFetch } from './client'

export async function submitFeedback({ requestId, endpoint, rating, comment = null }) {
  const { data } = await apiFetch('/feedback', {
    method: 'POST',
    body: JSON.stringify({ request_id: requestId, endpoint, rating, comment }),
  })
  return data  // { status: "recorded" }
  // NOTE: server returns HTTP 201 — apiFetch treats any 2xx as success, so this works fine.
}

export async function getQualityReport(days = 30) {
  const { data } = await apiFetch(`/quality-report?days=${days}`, { method: 'GET' })
  return data
}
```

---

## Part 12: Layout Components

### `src/components/layout/Layout.jsx`

```jsx
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import styles from './Layout.module.css'

export default function Layout({ health }) {
  return (
    <div className={styles.shell}>
      <TopBar health={health} />
      <div className={styles.body}>
        <Sidebar health={health} />
        <main className={styles.main} id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
```

```css
/* Layout.module.css */
.shell { display:flex; flex-direction:column; height:100vh; overflow:hidden; }
.body  { display:flex; flex:1; overflow:hidden; }
.main  { flex:1; overflow-y:auto; padding:var(--space-8); contain:layout style; }
@media (max-width:768px) { .main { padding:var(--space-4); } }
```

### `src/components/layout/TopBar.jsx`

```jsx
import StatusDot from '../ui/StatusDot'
import styles from './TopBar.module.css'

export default function TopBar({ health }) {
  const isHealthy = health?.status === 'ok'
  const mode = health?.mode ?? '—'

  function formatUptime(s) {
    if (!s) return '—'
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  }

  return (
    <header className={styles.topBar} role="banner">
      <div className={styles.left}>
        <StatusDot
          status={health === null ? 'unknown' : isHealthy ? 'ok' : 'error'}
          aria-label={`System: ${health === null ? 'checking' : isHealthy ? 'healthy' : 'degraded'}`}
        />
        <span className={styles.platformName}>AI Platform</span>
      </div>
      <div className={styles.right}>
        {health && (
          <>
            <span className={`${styles.modeBadge} ${styles[`mode_${mode}`]}`}>
              {mode.toUpperCase()}
            </span>
            <span className={styles.uptime} title="Uptime">↑ {formatUptime(health.uptime_seconds)}</span>
          </>
        )}
        <span className={styles.version}>{health?.version ?? ''}</span>
      </div>
    </header>
  )
}
```

```css
/* TopBar.module.css */
.topBar { height:52px; display:flex; align-items:center; justify-content:space-between; padding:0 var(--space-5); background:var(--bg-surface); border-bottom:1px solid var(--border-subtle); flex-shrink:0; gap:var(--space-4); }
.left,.right { display:flex; align-items:center; gap:var(--space-3); }
.platformName { font-size:0.9375rem; font-weight:600; color:var(--text-primary); }
.modeBadge { font-size:0.7rem; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; padding:3px 8px; border-radius:var(--radius-full); }
.mode_local  { background:var(--data-subtle);    color:var(--data); }
.mode_demo   { background:var(--accent-subtle);   color:var(--accent); }
.mode_prod   { background:var(--success-subtle);  color:var(--success); }
.uptime { font-size:0.8125rem; font-family:var(--font-mono); color:var(--text-muted); }
.version { font-size:0.75rem; font-family:var(--font-mono); color:var(--text-disabled); }
```

### `src/components/layout/Sidebar.jsx`

All routes are live. No "Soon" badges. Version reads from `health.version`.

```jsx
import { NavLink } from 'react-router-dom'
import styles from './Sidebar.module.css'

const NAV = [
  { to: '/',          icon: '◈', label: 'Dashboard',  desc: 'System health & overview' },
  { to: '/search',    icon: '⌕', label: 'Search',     desc: 'RAG search interface' },
  { to: '/agent',     icon: '⟳', label: 'Agent',      desc: 'Multi-step reasoning' },
  { to: '/ingest',    icon: '⇑', label: 'Ingest',     desc: 'Upload documents' },
  { to: '/analytics', icon: '▲', label: 'Analytics',  desc: 'Cost & usage analytics' },
  { to: '/documents', icon: '▤', label: 'Documents',  desc: 'Ingested document registry' },
]

export default function Sidebar({ health }) {
  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <div className={styles.logo}>
        <span className={styles.logoMark}>AI</span>
        <span className={styles.logoText}>Platform</span>
      </div>
      <ul className={styles.navList} role="list">
        {NAV.map(item => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
              title={item.desc}
            >
              <span className={styles.icon} aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
      <div className={styles.footer}>
        <span className={styles.version}>{health?.version ?? '—'}</span>
      </div>
    </nav>
  )
}
```

```css
/* Sidebar.module.css */
.sidebar { width:220px; flex-shrink:0; background:var(--bg-surface); border-right:1px solid var(--border-subtle); display:flex; flex-direction:column; padding:var(--space-4) 0; overflow-y:auto; }
.logo { display:flex; align-items:center; gap:var(--space-2); padding:var(--space-3) var(--space-5); margin-bottom:var(--space-4); border-bottom:1px solid var(--border-subtle); }
.logoMark { font-size:1rem; font-weight:800; color:var(--accent); background:var(--accent-subtle); border:1px solid var(--border-accent); padding:4px 8px; border-radius:var(--radius-sm); letter-spacing:0.05em; }
.logoText { font-size:0.9375rem; font-weight:600; color:var(--text-primary); }
.navList { list-style:none; flex:1; padding:0 var(--space-3); display:flex; flex-direction:column; gap:var(--space-1); }
.navItem { display:flex; align-items:center; gap:var(--space-3); padding:var(--space-2) var(--space-3); border-radius:var(--radius-md); color:var(--text-muted); text-decoration:none; font-size:0.875rem; font-weight:500; border:1px solid transparent; transition:var(--transition-fast); }
.navItem:hover { color:var(--text-primary); background:var(--bg-elevated); }
.navItem.active { color:var(--accent); background:var(--accent-subtle); border-color:var(--border-accent); }
.icon { font-size:1rem; width:20px; text-align:center; flex-shrink:0; }
.footer { padding:var(--space-4) var(--space-5); border-top:1px solid var(--border-subtle); margin-top:auto; }
.version { font-size:0.75rem; color:var(--text-disabled); font-family:var(--font-mono); }
```

---

## Part 13: UI Primitive Components

### `src/components/ui/StatusDot.jsx`

```jsx
import styles from './StatusDot.module.css'
export default function StatusDot({ status = 'unknown', animated = true, size = 'md' }) {
  return (
    <span
      className={[styles.dot, styles[status], styles[size], animated ? styles.animated : ''].join(' ')}
      role="img"
      aria-label={`Status: ${status}`}
    />
  )
}
```

```css
/* StatusDot.module.css */
.dot { display:inline-block; border-radius:50%; flex-shrink:0; }
.sm{width:7px;height:7px} .md{width:9px;height:9px} .lg{width:12px;height:12px}
.ok{background:var(--success)} .error{background:var(--danger)} .unknown{background:var(--text-disabled)} .warning{background:var(--warning)}
.animated.ok { animation:pulse-dot 2s ease-in-out infinite; box-shadow:0 0 0 0 rgba(16,185,129,0.4); }
```

### `src/components/ui/Badge.jsx`

```jsx
import styles from './Badge.module.css'
export default function Badge({ children, variant = 'neutral', size = 'md', title, className = '' }) {
  return (
    <span className={[styles.badge, styles[variant], styles[size], className].join(' ')} title={title}>
      {children}
    </span>
  )
}
```

```css
/* Badge.module.css */
.badge { display:inline-flex; align-items:center; gap:4px; font-weight:600; border-radius:var(--radius-full); white-space:nowrap; border:1px solid transparent; }
.sm{font-size:0.7rem;padding:2px 7px} .md{font-size:0.75rem;padding:3px 10px}
.success { background:var(--badge-hit-bg);  color:var(--badge-hit-text); }
.danger  { background:var(--danger-subtle); color:var(--red-400); }
.warning { background:var(--warning-subtle);color:var(--yellow-400); }
.info    { background:var(--data-subtle);   color:var(--data); }
.accent  { background:var(--accent-subtle); color:var(--accent); }
.neutral { background:var(--badge-miss-bg); color:var(--badge-miss-text); }
```

### `src/components/ui/Card.jsx`

```jsx
import styles from './Card.module.css'
export default function Card({ children, className = '', title, accent = false }) {
  return (
    <section className={[styles.card, accent ? styles.accent : '', className].join(' ')} aria-label={title}>
      {title && <h3 className={styles.title}>{title}</h3>}
      {children}
    </section>
  )
}
```

```css
/* Card.module.css */
.card { background:var(--card-bg); border:1px solid var(--card-border); border-radius:var(--radius-lg); padding:var(--space-5); transition:border-color var(--transition-fast); }
.card.accent { border-color:var(--border-accent); box-shadow:var(--shadow-accent); }
.title { font-size:0.8125rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-muted); margin-bottom:var(--space-4); }
```

### `src/components/ui/Button.jsx`

```jsx
import styles from './Button.module.css'
export default function Button({ children, variant = 'primary', size = 'md', disabled = false, loading = false, onClick, type = 'button', className = '', ...props }) {
  return (
    <button type={type} className={[styles.btn, styles[variant], styles[size], className].join(' ')} disabled={disabled || loading} onClick={onClick} aria-busy={loading} {...props}>
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
      {children}
    </button>
  )
}
```

```css
/* Button.module.css */
.btn { display:inline-flex; align-items:center; justify-content:center; gap:var(--space-2); font-family:var(--font-sans); font-weight:600; border:1px solid transparent; border-radius:var(--radius-md); cursor:pointer; white-space:nowrap; transition:var(--transition-fast); }
.btn:disabled { opacity:0.4; cursor:not-allowed; }
.sm{font-size:0.8125rem;padding:var(--space-1) var(--space-3)} .md{font-size:0.875rem;padding:var(--space-2) var(--space-5)} .lg{font-size:0.9375rem;padding:var(--space-3) var(--space-6)}
.primary { background:var(--btn-primary-bg); color:var(--btn-primary-text); }
.primary:hover:not(:disabled) { background:var(--btn-primary-hover); }
.secondary { background:var(--bg-elevated); color:var(--text-primary); border-color:var(--border-default); }
.secondary:hover:not(:disabled) { border-color:var(--border-strong); }
.ghost { background:transparent; color:var(--text-secondary); }
.ghost:hover:not(:disabled) { background:var(--btn-ghost-hover); color:var(--text-primary); }
.danger { background:var(--danger-subtle); color:var(--red-400); border-color:rgba(239,68,68,0.2); }
.spinner { width:14px; height:14px; border:2px solid rgba(255,255,255,0.3); border-top-color:currentColor; border-radius:50%; animation:spin 0.7s linear infinite; }
```

### `src/components/ui/Toggle.jsx`

```jsx
import styles from './Toggle.module.css'
export default function Toggle({ label, checked, onChange, disabled = false, id }) {
  const tid = id || `toggle-${label?.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <div className={styles.wrapper}>
      <label className={styles.label} htmlFor={tid}>{label}</label>
      <button id={tid} role="switch" aria-checked={checked} disabled={disabled}
        className={`${styles.track} ${checked ? styles.on : styles.off}`}
        onClick={() => onChange?.(!checked)} type="button">
        <span className={styles.thumb} />
        <span className="sr-only">{checked ? 'On' : 'Off'}</span>
      </button>
    </div>
  )
}
```

```css
/* Toggle.module.css */
.wrapper { display:flex; align-items:center; justify-content:space-between; gap:var(--space-3); }
.label { font-size:0.875rem; color:var(--text-secondary); font-weight:500; }
.track { position:relative; width:40px; height:22px; border-radius:var(--radius-full); border:none; cursor:pointer; transition:background var(--transition-fast); flex-shrink:0; }
.on{background:var(--accent)} .off{background:var(--gray-700)}
.track:disabled { opacity:0.35; cursor:not-allowed; }
.thumb { position:absolute; top:3px; left:3px; width:16px; height:16px; border-radius:50%; background:white; transition:transform var(--transition-fast); box-shadow:0 1px 3px rgba(0,0,0,0.3); }
.on .thumb{transform:translateX(18px)} .off .thumb{transform:translateX(0)}
```

---

## Part 14: Search Feature Components

### `src/components/search/MetaBar.jsx`

```jsx
import Badge from '../ui/Badge'
import styles from './MetaBar.module.css'

export default function MetaBar({ headers }) {
  if (!headers) return null
  const { cache, cacheType, costUsd, tokensIn, tokensOut, processTime, queryId, budgetRemaining, budgetLimit } = headers
  const isHit = cache === 'HIT'

  function formatCost(v) {
    const n = parseFloat(v)
    return isNaN(n) ? null : `$${n.toFixed(6)}`
  }
  function formatBudget(r, l) {
    if (!r || !l) return null
    return `${Math.round(parseInt(r)/1000)}K / ${Math.round(parseInt(l)/1000)}K tokens`
  }

  return (
    <div className={styles.metaBar} role="status" aria-label="Query metadata">
      {cache && (
        <Badge variant={isHit ? 'success' : 'neutral'} title={isHit ? 'Cache hit — no LLM call' : 'Cache miss — full RAG pipeline'}>
          {isHit ? `⚡ ${cacheType === 'semantic' ? 'Semantic' : 'Exact'} Hit` : '↻ Cache Miss'}
        </Badge>
      )}
      {costUsd && parseFloat(costUsd) >= 0 && (
        <span className={styles.chip} title="LLM cost">
          <span className={styles.label}>Cost</span>
          <span className={styles.value} style={{color:'var(--accent)'}}>{formatCost(costUsd) ?? '$0.000000'}</span>
        </span>
      )}
      {tokensIn && tokensOut && (
        <span className={styles.chip} title="Token usage">
          <span className={styles.label}>Tokens</span>
          <span className={styles.value} style={{color:'var(--data)'}}>{tokensIn} in / {tokensOut} out</span>
        </span>
      )}
      {processTime && (
        <span className={styles.chip} title="Response time">
          <span className={styles.label}>Time</span>
          <span className={styles.value}>{processTime}</span>
        </span>
      )}
      {budgetRemaining && budgetLimit && (
        <span className={styles.chip} title="Daily token budget remaining">
          <span className={styles.label}>Budget</span>
          <span className={styles.value}>{formatBudget(budgetRemaining, budgetLimit)}</span>
        </span>
      )}
      {queryId && (
        <span className={styles.chip} title={`Request ID: ${queryId}`}>
          <span className={styles.label}>ID</span>
          <span className={`${styles.value} ${styles.mono}`}>{queryId.slice(0,12)}…</span>
        </span>
      )}
    </div>
  )
}
```

```css
/* MetaBar.module.css */
.metaBar { display:flex; flex-wrap:wrap; align-items:center; gap:var(--space-2); padding:var(--space-3) 0; border-top:1px solid var(--border-subtle); margin-top:var(--space-4); }
.chip { display:inline-flex; align-items:center; gap:5px; font-size:0.75rem; padding:3px 9px; background:var(--bg-sunken); border:1px solid var(--border-subtle); border-radius:var(--radius-full); }
.label { color:var(--text-disabled); font-weight:500; }
.value { color:var(--text-secondary); font-weight:600; }
.mono { font-family:var(--font-mono); }
```

### `src/components/search/ConfidenceGauge.jsx`

```jsx
import styles from './ConfidenceGauge.module.css'

export default function ConfidenceGauge({ confidence, floor = 0.45 }) {
  if (confidence == null) return null
  const pct = Math.round(confidence * 100)
  const level = confidence >= 0.75 ? 'high' : confidence >= floor ? 'medium' : 'low'
  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.label}>Confidence</span>
        <span className={`${styles.value} ${styles[level]}`}>{pct}%</span>
      </div>
      <div className={styles.track} role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`${styles.fill} ${styles[level]}`} style={{width:`${pct}%`}} />
        <div className={styles.threshold} style={{left:`${floor*100}%`}} title={`Guardrail floor: ${floor*100}%`} />
      </div>
      <span className={styles.floorLabel} style={{left:`${floor*100}%`}}>{floor*100}% floor</span>
    </div>
  )
}
```

```css
/* ConfidenceGauge.module.css */
.wrapper { display:flex; flex-direction:column; gap:var(--space-2); position:relative; }
.header { display:flex; justify-content:space-between; align-items:center; }
.label { font-size:0.8125rem; color:var(--text-muted); font-weight:500; }
.value { font-size:0.9375rem; font-weight:700; font-family:var(--font-mono); }
.value.high{color:var(--success)} .value.medium{color:var(--accent)} .value.low{color:var(--danger)}
.track { position:relative; height:8px; background:var(--bg-sunken); border-radius:var(--radius-full); overflow:visible; }
.fill { height:100%; border-radius:var(--radius-full); transition:width 600ms cubic-bezier(0.34,1.56,0.64,1); }
.fill.high{background:var(--success)} .fill.medium{background:var(--accent)} .fill.low{background:var(--danger)}
.threshold { position:absolute; top:-4px; bottom:-4px; width:2px; background:var(--text-muted); border-radius:var(--radius-full); transform:translateX(-50%); pointer-events:none; }
.floorLabel { position:absolute; bottom:-18px; font-size:0.65rem; color:var(--text-disabled); transform:translateX(-50%); white-space:nowrap; }
```

### `src/components/search/GuardrailBanner.jsx`

```jsx
import styles from './GuardrailBanner.module.css'
export default function GuardrailBanner({ type, reason, confidence, floor = 0.45 }) {
  if (type === 'blocked') return (
    <div className={`${styles.banner} ${styles.error}`} role="alert">
      <span className={styles.icon}>⊘</span>
      <div><strong>Query blocked</strong><p>{reason || 'This query matches a restricted pattern.'}</p></div>
    </div>
  )
  if (type === 'flagged') return (
    <div className={`${styles.banner} ${styles.warning}`} role="status">
      <span className={styles.icon}>⚠</span>
      <div>
        <strong>Low confidence answer</strong>
        <p>{reason || `Confidence ${confidence != null ? Math.round(confidence*100)+'%' : ''} is below the ${floor*100}% threshold. Verify against primary sources.`}</p>
      </div>
    </div>
  )
  if (type === 'clarification') return (
    <div className={`${styles.banner} ${styles.info}`} role="status">
      <span className={styles.icon}>◎</span>
      <div><strong>Clarification suggested</strong><p>Query is ambiguous — try rephrasing for a more precise answer.</p></div>
    </div>
  )
  return null
}
```

```css
/* GuardrailBanner.module.css */
.banner { display:flex; align-items:flex-start; gap:var(--space-3); padding:var(--space-4); border-radius:var(--radius-md); border:1px solid; animation:fadeIn 200ms ease; }
.banner strong { display:block; font-size:0.875rem; margin-bottom:var(--space-1); }
.banner p { font-size:0.8125rem; margin:0; opacity:0.85; }
.icon { font-size:1.1rem; flex-shrink:0; margin-top:1px; }
.error   { background:var(--danger-subtle);  border-color:rgba(239,68,68,0.25);  color:var(--red-400); }
.warning { background:var(--warning-subtle); border-color:rgba(234,179,8,0.25);  color:var(--yellow-400); }
.info    { background:var(--data-subtle);    border-color:rgba(34,211,238,0.2);  color:var(--data); }
```

### `src/components/search/AnswerBlock.jsx`

```jsx
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import styles from './AnswerBlock.module.css'

export default function AnswerBlock({ answer, isStreaming = false }) {
  if (!answer) return null
  return (
    <div className={styles.wrapper}>
      <div className={`${styles.answer} ${isStreaming ? styles.streaming : ''}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
        {isStreaming && <span className="cursor" aria-hidden="true" />}
      </div>
    </div>
  )
}
```

```css
/* AnswerBlock.module.css */
.wrapper { padding:var(--space-5); background:var(--bg-elevated); border-radius:var(--radius-lg); border:1px solid var(--border-default); border-left:3px solid var(--accent); }
.answer { font-size:0.9375rem; line-height:1.7; color:var(--text-primary); }
.answer :global(p) { margin-bottom:var(--space-3); color:var(--text-primary); }
.answer :global(p:last-child) { margin-bottom:0; }
.answer :global(strong) { font-weight:700; }
.answer :global(code) { font-family:var(--font-mono); font-size:0.85em; background:var(--bg-sunken); padding:2px 6px; border-radius:var(--radius-sm); color:var(--accent); }
.answer :global(pre) { background:var(--bg-sunken); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:var(--space-4); overflow-x:auto; margin:var(--space-4) 0; }
.answer :global(pre code) { background:none; padding:0; color:var(--text-primary); }
.answer :global(ul),.answer :global(ol) { padding-left:var(--space-6); margin-bottom:var(--space-3); }
.answer :global(li) { margin-bottom:var(--space-1); color:var(--text-primary); }
.answer :global(table) { width:100%; border-collapse:collapse; font-size:0.875rem; margin:var(--space-4) 0; }
.answer :global(th),.answer :global(td) { padding:var(--space-2) var(--space-3); border:1px solid var(--border-subtle); }
.answer :global(th) { background:var(--bg-sunken); font-weight:600; color:var(--text-secondary); }
.answer :global(blockquote) { border-left:3px solid var(--border-strong); padding-left:var(--space-4); color:var(--text-muted); margin:var(--space-4) 0; }
```

### `src/components/search/CitationCard.jsx`

```jsx
import { useState } from 'react'
import Badge from '../ui/Badge'
import styles from './CitationCard.module.css'

export default function CitationCard({ result, index }) {
  const [expanded, setExpanded] = useState(false)
  const { document_id, namespace, content, score, metadata } = result
  const chunkIndex = metadata?.chunk_index

  function scoreVariant(s) {
    if (s > 0.85) return 'success'
    if (s > 0.70) return 'info'
    if (s > 0.50) return 'warning'
    return 'neutral'
  }
  // RRF scores are <0.1; vector scores are 0.1-1.0
  function formatScore(s) {
    return s < 0.1 ? s.toFixed(4) : `${Math.round(s*100)}%`
  }
  const preview = content.slice(0, 180)

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.source}>
          <span className={styles.index} aria-label={`Citation ${index+1}`}>[{index+1}]</span>
          <span className={styles.docId} title={document_id}>{document_id}</span>
          {chunkIndex != null && <span className={styles.chunk}>chunk #{chunkIndex}</span>}
        </div>
        <div className={styles.meta}>
          <Badge variant="neutral" size="sm">{namespace}</Badge>
          <Badge variant={scoreVariant(score)} size="sm" title={`Score: ${score}`}>{formatScore(score)}</Badge>
        </div>
      </div>
      <div className={styles.content}>
        <p className={styles.text}>{expanded ? content : preview}{!expanded && content.length > 180 && '…'}</p>
        {content.length > 180 && (
          <button className={styles.expandBtn} onClick={() => setExpanded(e => !e)} aria-expanded={expanded}>
            {expanded ? 'Show less' : 'Show full excerpt'}
          </button>
        )}
      </div>
    </div>
  )
}
```

```css
/* CitationCard.module.css */
.card { background:var(--bg-surface); border:1px solid var(--border-default); border-radius:var(--radius-md); padding:var(--space-4); display:flex; flex-direction:column; gap:var(--space-3); animation:fadeIn 200ms ease; transition:border-color var(--transition-fast); }
.card:hover { border-color:var(--border-strong); }
.header { display:flex; align-items:center; justify-content:space-between; gap:var(--space-3); flex-wrap:wrap; }
.source { display:flex; align-items:center; gap:var(--space-2); min-width:0; }
.index { font-family:var(--font-mono); font-size:0.8rem; font-weight:700; color:var(--accent); flex-shrink:0; }
.docId { font-size:0.875rem; font-weight:600; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:260px; }
.chunk { font-size:0.75rem; color:var(--text-disabled); font-family:var(--font-mono); }
.meta { display:flex; gap:var(--space-2); flex-shrink:0; }
.text { font-size:0.875rem; line-height:1.6; color:var(--text-secondary); font-family:var(--font-mono); white-space:pre-wrap; word-break:break-word; }
.expandBtn { background:none; border:none; color:var(--accent); font-size:0.8125rem; font-weight:500; cursor:pointer; padding:0; margin-top:var(--space-2); font-family:var(--font-sans); }
.expandBtn:hover { text-decoration:underline; }
```

### `src/components/search/SearchForm.jsx`

Namespace list from `config.namespaces` (flat key map). Falls back to `['default']` while config loads.

```jsx
import { useState } from 'react'
import Button from '../ui/Button'
import Toggle from '../ui/Toggle'
import styles from './SearchForm.module.css'

const MODES = [
  { value: 'hybrid',      label: 'Hybrid', tooltip: 'BM25 + vector via RRF — best quality' },
  { value: 'vector_only', label: 'Vector', tooltip: 'Semantic similarity only' },
  { value: 'bm25_only',   label: 'BM25',   tooltip: 'Exact keyword matching' },
]

export default function SearchForm({ onSubmit, loading, config }) {
  const namespaces = config?.namespaces ? Object.keys(config.namespaces) : ['default']
  const rerankerEnabled = config?.reranker_enabled ?? true
  const maxQueryLength = config?.max_query_length ?? 1000

  const [query, setQuery]       = useState('')
  const [namespace, setNs]      = useState(namespaces[0])
  const [topK, setTopK]         = useState(5)
  const [mode, setMode]         = useState('hybrid')
  const [rerank, setRerank]     = useState(true)

  function handleKeyDown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); handleSubmit(e) }
  }
  function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim() || loading) return
    onSubmit({ query: query.trim(), namespace, topK, retrievalMode: mode, rerank: rerank && rerankerEnabled })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Search form">
      <div className={styles.inputRow}>
        <textarea className={styles.textarea} value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown} placeholder="Ask a question about your documents…"
          rows={3} maxLength={maxQueryLength} aria-label="Search query"
          aria-describedby="q-hint" disabled={loading} />
        <Button type="submit" loading={loading} disabled={!query.trim()} size="lg">Search</Button>
      </div>
      <span id="q-hint" className={styles.hint}>Ctrl+Enter · Max {maxQueryLength} chars</span>
      <div className={styles.controls}>
        <label className={styles.group}>
          <span className={styles.cLabel}>Namespace</span>
          <select className={styles.select} value={namespace} onChange={e => setNs(e.target.value)} disabled={!config}>
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        </label>
        <label className={styles.group}>
          <span className={styles.cLabel}>Retrieval</span>
          <div className={styles.modeGroup} role="radiogroup" aria-label="Retrieval mode">
            {MODES.map(m => (
              <button key={m.value} type="button" title={m.tooltip} aria-pressed={mode === m.value}
                className={`${styles.modeBtn} ${mode === m.value ? styles.active : ''}`}
                onClick={() => setMode(m.value)}>{m.label}</button>
            ))}
          </div>
        </label>
        <label className={styles.group}>
          <span className={styles.cLabel}>Sources: {topK}</span>
          <input type="range" min={1} max={20} value={topK} onChange={e => setTopK(Number(e.target.value))} className={styles.slider} aria-label={`Top ${topK} sources`} />
        </label>
        <div className={styles.group}>
          <Toggle label="Rerank" checked={rerank && rerankerEnabled} onChange={setRerank} disabled={!rerankerEnabled} id="rerank-toggle" />
          {!rerankerEnabled && <span className={styles.disabledHint}>Unavailable in this mode</span>}
        </div>
      </div>
    </form>
  )
}
```

---

## Part 15: Ingest Feature Components

### `src/components/ingest/DropZone.jsx`

```jsx
import { useState, useRef } from 'react'
import Button from '../ui/Button'
import styles from './DropZone.module.css'

const ACCEPTED = ['.txt', '.md', '.pdf']

export default function DropZone({ onUpload, loading, config }) {
  const namespaces = config?.namespaces ? Object.keys(config.namespaces) : ['default']
  const [dragging, setDragging] = useState(false)
  const [file, setFile]         = useState(null)
  const [namespace, setNs]      = useState(namespaces[0])
  const [docId, setDocId]       = useState('')
  const inputRef = useRef(null)

  function handleDrop(e) { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) setFile(f) }
  function fileSize(b) { return b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB` }

  return (
    <form onSubmit={e => { e.preventDefault(); if (file && !loading) onUpload({ file, namespace, documentId: docId || undefined }) }} aria-label="Document upload">
      <div className={[styles.zone, dragging ? styles.dragging : '', file ? styles.hasFile : ''].join(' ')}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !file && inputRef.current?.click()}
        role="button" tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
        aria-label="Drop file here or click to browse">
        <input ref={inputRef} type="file" accept={ACCEPTED.join(',')} className={styles.hidden} onChange={e => { const f = e.target.files[0]; if (f) setFile(f) }} aria-hidden="true" />
        {file ? (
          <div className={styles.fileInfo}>
            <span className={styles.fileName}>{file.name}</span>
            <span className={styles.fileSize}>{fileSize(file.size)}</span>
            <button type="button" className={styles.clearBtn} onClick={e => { e.stopPropagation(); setFile(null) }} aria-label="Remove file">✕</button>
          </div>
        ) : (
          <div className={styles.prompt}>
            <span className={styles.icon} aria-hidden="true">⇑</span>
            <span>Drop a file here, or click to browse</span>
            <span className={styles.hint}>Accepts: {ACCEPTED.join(', ')}</span>
          </div>
        )}
      </div>
      <div className={styles.options}>
        <label className={styles.optGroup}>
          <span className={styles.optLabel}>Namespace</span>
          <select className={styles.select} value={namespace} onChange={e => setNs(e.target.value)} disabled={!config}>
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        </label>
        <label className={styles.optGroup}>
          <span className={styles.optLabel}>Document ID (optional)</span>
          <input type="text" className={styles.input} value={docId} onChange={e => setDocId(e.target.value)} placeholder={file?.name || 'defaults to filename'} />
        </label>
      </div>
      <Button type="submit" disabled={!file} loading={loading} size="lg">Ingest Document</Button>
    </form>
  )
}
```

### `src/components/ingest/IngestResult.jsx`

```jsx
import Badge from '../ui/Badge'
import Card from '../ui/Card'
import styles from './IngestResult.module.css'

const STATUS = {
  new:       { label: 'New Document', variant: 'success', desc: 'Ingested and indexed for the first time.' },
  updated:   { label: 'Updated',      variant: 'info',    desc: 'Existing document replaced with new content.' },
  unchanged: { label: 'Unchanged',    variant: 'neutral', desc: 'Identical to stored version — no re-ingestion needed.' },
}

export default function IngestResult({ result }) {
  if (!result) return null
  const { document_id, namespace, total_chunks, total_time_seconds,
          throughput_chunks_per_second, status, content_hash, chunks_deleted } = result
  const cfg = STATUS[status] ?? STATUS.new

  return (
    <Card title="Ingestion Complete">
      <div className={styles.statusRow}>
        <Badge variant={cfg.variant}>{cfg.label}</Badge>
        <span className={styles.desc}>{cfg.desc}</span>
      </div>
      <dl className={styles.metrics}>
        <div className={styles.metric}><dt>Document</dt><dd>{document_id}</dd></div>
        <div className={styles.metric}><dt>Namespace</dt><dd>{namespace}</dd></div>
        <div className={styles.metric}><dt>Chunks created</dt><dd className={styles.highlight}>{total_chunks.toLocaleString()}</dd></div>
        {chunks_deleted > 0 && <div className={styles.metric}><dt>Old chunks removed</dt><dd>{chunks_deleted.toLocaleString()}</dd></div>}
        <div className={styles.metric}><dt>Processing time</dt><dd>{total_time_seconds.toFixed(2)}s</dd></div>
        <div className={styles.metric}><dt>Throughput</dt><dd>{throughput_chunks_per_second.toFixed(1)} chunks/sec</dd></div>
        {content_hash && (
          <div className={`${styles.metric} ${styles.hashRow}`}>
            <dt>SHA-256</dt>
            <dd className={styles.hash} title={content_hash}>{content_hash.slice(0,16)}…</dd>
          </div>
        )}
      </dl>
    </Card>
  )
}
```

---

## Part 16: Agent Feature Components

### `src/components/agent/VerificationBadge.jsx`

```jsx
import styles from './VerificationBadge.module.css'
export default function VerificationBadge({ verified, notes }) {
  const state = verified === null || verified === undefined ? 'skipped' : verified ? 'verified' : 'failed'
  const icon  = { verified: '✓', failed: '✗', skipped: '◎' }[state]
  const label = { verified: 'Verified', failed: 'Unverified', skipped: 'Verifier not run' }[state]
  return (
    <div className={`${styles.badge} ${styles[state]}`}>
      <span className={styles.icon}>{icon}</span>
      <span>{label}</span>
      {notes && <span className={styles.notes}>{notes}</span>}
    </div>
  )
}
```

```css
/* VerificationBadge.module.css */
.badge { display:inline-flex; align-items:center; gap:var(--space-2); padding:var(--space-2) var(--space-3); border-radius:var(--radius-md); border:1px solid; font-size:0.875rem; font-weight:600; }
.verified { background:var(--success-subtle); border-color:rgba(16,185,129,0.25); color:var(--success); }
.failed   { background:var(--danger-subtle);  border-color:rgba(239,68,68,0.25);  color:var(--red-400); }
.skipped  { background:var(--bg-elevated);    border-color:var(--border-default); color:var(--text-muted); }
.icon { font-size:1rem; }
.notes { font-size:0.8rem; font-weight:400; opacity:0.8; }
```

### `src/components/agent/ReasoningChain.jsx`

```jsx
import { useState } from 'react'
import styles from './ReasoningChain.module.css'

export default function ReasoningChain({ steps = [], toolCallCount }) {
  const [open, setOpen] = useState(false)
  if (!steps.length) return null
  return (
    <div className={styles.chain}>
      <button className={styles.toggle} onClick={() => setOpen(o => !o)} aria-expanded={open}>
        <span className={styles.arrow}>{open ? '▾' : '▸'}</span>
        Reasoning chain
        <span className={styles.count}>{toolCallCount} tool call{toolCallCount !== 1 ? 's' : ''}</span>
      </button>
      {open && (
        <ol className={styles.steps}>
          {steps.map((step, i) => {
            const isCall   = step.startsWith('Called tool:')
            const isResult = step.startsWith('Tool result:')
            return (
              <li key={i} className={`${styles.step} ${isCall ? styles.call : isResult ? styles.result : styles.note}`}>
                <span className={styles.stepIcon} aria-hidden="true">{isCall ? '⚙' : isResult ? '↩' : '◦'}</span>
                <span className={styles.text}>{step}</span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
```

```css
/* ReasoningChain.module.css */
.chain { border:1px solid var(--border-subtle); border-radius:var(--radius-md); overflow:hidden; }
.toggle { width:100%; display:flex; align-items:center; gap:var(--space-2); padding:var(--space-3) var(--space-4); background:var(--bg-surface); border:none; cursor:pointer; color:var(--text-muted); font-size:0.875rem; font-weight:600; text-align:left; }
.toggle:hover { background:var(--bg-elevated); }
.arrow { color:var(--accent); font-size:0.75rem; }
.count { margin-left:auto; font-size:0.75rem; background:var(--bg-elevated); color:var(--text-secondary); padding:2px 8px; border-radius:var(--radius-full); }
.steps { list-style:none; padding:var(--space-3) var(--space-4); display:flex; flex-direction:column; gap:var(--space-2); }
.step { display:flex; align-items:flex-start; gap:var(--space-2); font-size:0.8125rem; line-height:1.5; }
.call .stepIcon { color:var(--accent); } .result .stepIcon { color:var(--data); }
.stepIcon { flex-shrink:0; margin-top:2px; }
.text { color:var(--text-secondary); font-family:var(--font-mono); word-break:break-word; }
```

### `src/components/agent/AgentCitationCard.jsx`

```jsx
import { useState } from 'react'
import Badge from '../ui/Badge'
import styles from './AgentCitationCard.module.css'

export default function AgentCitationCard({ citation, index }) {
  const [expanded, setExpanded] = useState(false)
  const { document_id, source_filename, chunk_index, relevance_score, excerpt } = citation
  const pct  = Math.round(relevance_score * 100)
  const variant = relevance_score > 0.85 ? 'success' : relevance_score > 0.70 ? 'info' : relevance_score > 0.50 ? 'warning' : 'neutral'

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.index}>[{index+1}]</span>
        <div className={styles.meta}>
          <span className={styles.filename}>{source_filename || document_id}</span>
          <span className={styles.chunk}>chunk #{chunk_index}</span>
        </div>
        <Badge variant={variant} size="sm" title={`Relevance: ${relevance_score}`}>{pct}%</Badge>
      </div>
      <p className={styles.excerpt}>{expanded ? excerpt : excerpt?.slice(0,200)}{!expanded && excerpt?.length > 200 && '…'}</p>
      {excerpt?.length > 200 && (
        <button className={styles.expand} onClick={() => setExpanded(e => !e)}>
          {expanded ? 'Show less' : 'Show full excerpt'}
        </button>
      )}
    </div>
  )
}
```

### `src/components/agent/AgentForm.jsx`

```jsx
import { useState } from 'react'
import Button from '../ui/Button'
import Toggle from '../ui/Toggle'
import styles from './AgentForm.module.css'

export default function AgentForm({ onSubmit, loading, config }) {
  const namespaces = config?.namespaces ? Object.keys(config.namespaces) : ['default']
  const defaults   = config?.agent_defaults ?? { max_iterations: 6, enable_verifier: true, max_verify_retries: 1 }

  const [question, setQ]        = useState('')
  const [namespace, setNs]      = useState(namespaces[0])
  const [maxIter, setMaxIter]   = useState(defaults.max_iterations)
  const [verifier, setVerifier] = useState(defaults.enable_verifier)
  const [retries, setRetries]   = useState(defaults.max_verify_retries)

  function handleSubmit(e) {
    e.preventDefault()
    if (!question.trim() || loading) return
    onSubmit({ question: question.trim(), namespace, maxIterations: maxIter, enableVerifier: verifier, maxVerifyRetries: retries })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Agent query">
      <textarea className={styles.textarea} value={question} onChange={e => setQ(e.target.value)}
        placeholder="Ask a complex compliance question… The agent researches iteratively."
        rows={3} maxLength={config?.max_query_length ?? 1000} disabled={loading} aria-label="Agent question" />
      <div className={styles.controls}>
        <label className={styles.group}>
          <span className={styles.label}>Namespace</span>
          <select className={styles.select} value={namespace} onChange={e => setNs(e.target.value)} disabled={!config}>
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        </label>
        <label className={styles.group}>
          <span className={styles.label}>Max iterations: {maxIter}</span>
          <input type="range" min={1} max={10} value={maxIter} onChange={e => setMaxIter(Number(e.target.value))} className={styles.slider} />
        </label>
        <div className={styles.group}>
          <Toggle label="Enable verifier" checked={verifier} onChange={setVerifier} id="verifier-toggle" />
        </div>
        {verifier && (
          <label className={styles.group}>
            <span className={styles.label}>Verify retries: {retries}</span>
            <input type="range" min={0} max={3} value={retries} onChange={e => setRetries(Number(e.target.value))} className={styles.slider} />
          </label>
        )}
      </div>
      <Button type="submit" loading={loading} disabled={!question.trim()} size="lg">Run Agent</Button>
    </form>
  )
}
```

---

## Part 17: Feedback Component

### `src/components/feedback/FeedbackButtons.jsx`

Used on both Search and Agent result blocks. Needs `X-Query-ID` from response headers.

```jsx
import { useState } from 'react'
import { submitFeedback } from '../../api/feedback'
import styles from './FeedbackButtons.module.css'

export default function FeedbackButtons({ requestId, endpoint }) {
  const [sent, setSent]   = useState(null)  // null | 'up' | 'down'
  const [error, setError] = useState(false)

  if (!requestId) return null  // no ID = no feedback

  async function handleRate(rating) {
    if (sent) return
    try {
      await submitFeedback({ requestId, endpoint, rating })
      setSent(rating)
    } catch { setError(true) }
  }

  return (
    <div className={styles.row} role="group" aria-label="Rate this answer">
      <button className={`${styles.btn} ${sent === 'up' ? styles.active : ''}`}
        onClick={() => handleRate('up')} disabled={!!sent} aria-pressed={sent === 'up'} title="Helpful">
        👍
      </button>
      <button className={`${styles.btn} ${sent === 'down' ? styles.active : ''}`}
        onClick={() => handleRate('down')} disabled={!!sent} aria-pressed={sent === 'down'} title="Not helpful">
        👎
      </button>
      {sent && <span className={styles.thanks}>Thanks for the feedback</span>}
      {error && <span className={styles.err}>Couldn't submit — try again</span>}
    </div>
  )
}
```

```css
/* FeedbackButtons.module.css */
.row { display:flex; align-items:center; gap:var(--space-2); }
.btn { background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:var(--radius-sm); padding:4px 10px; cursor:pointer; font-size:1rem; transition:var(--transition-fast); }
.btn:hover:not(:disabled) { border-color:var(--border-strong); }
.btn:disabled { opacity:0.5; cursor:default; }
.btn.active { background:var(--accent-subtle); border-color:var(--border-accent); }
.thanks { font-size:0.8125rem; color:var(--success); }
.err { font-size:0.8125rem; color:var(--danger); }
```

---

## Part 18: Pages

### `src/pages/Dashboard.jsx`

```jsx
import { useState, useEffect } from 'react'
import { getHealth } from '../api/health'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import StatusDot from '../components/ui/StatusDot'
import styles from './Dashboard.module.css'

export default function Dashboard({ health }) {
  // health is already fetched in App.jsx and passed as prop.
  // We do NOT fetch it again here.
  const [localHealth, setLocal] = useState(health)
  useEffect(() => { setLocal(health) }, [health])

  const services = localHealth ? [
    { name: 'Database', status: localHealth.db    === 'ok' ? 'ok' : 'error', detail: localHealth.db },
    { name: 'Redis',    status: localHealth.redis  === 'ok' ? 'ok' : 'error', detail: localHealth.redis },
    { name: 'API',      status: 'ok', detail: `v${localHealth.version}` },
  ] : []

  function formatUptime(s) {
    if (!s) return '—'
    const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60)
    if (d > 0) return `${d}d ${h}h`
    if (h > 0) return `${h}h ${m}m`
    return `${m}m ${s%60}s`
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Dashboard</h1>
        <p>System health and platform overview</p>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sTitle}>System Health</h2>
        <div className={styles.healthGrid}>
          {services.length === 0
            ? Array.from({length:3}, (_,i) => <div key={i} className="skeleton" style={{height:100}} />)
            : services.map(s => (
              <Card key={s.name}>
                <div className={styles.svcHeader}>
                  <StatusDot status={s.status} />
                  <span className={styles.svcName}>{s.name}</span>
                </div>
                <span className={s.status === 'ok' ? styles.ok : styles.err}>
                  {s.status === 'ok' ? 'Operational' : s.detail}
                </span>
              </Card>
            ))
          }
        </div>
      </section>

      {localHealth && (
        <section className={styles.section}>
          <h2 className={styles.sTitle}>Platform Info</h2>
          <div className={styles.infoGrid}>
            <Card>
              <dt className={styles.infoLabel}>Mode</dt>
              <dd><Badge variant={localHealth.mode === 'prod' ? 'success' : localHealth.mode === 'demo' ? 'accent' : 'info'}>{localHealth.mode?.toUpperCase()}</Badge></dd>
            </Card>
            <Card>
              <dt className={styles.infoLabel}>Uptime</dt>
              <dd className={styles.infoVal}>{formatUptime(localHealth.uptime_seconds)}</dd>
            </Card>
            <Card>
              <dt className={styles.infoLabel}>Version</dt>
              <dd className={`${styles.infoVal} ${styles.mono}`}>{localHealth.version}</dd>
            </Card>
            <Card>
              <dt className={styles.infoLabel}>Overall</dt>
              <dd><Badge variant={localHealth.status === 'ok' ? 'success' : 'danger'}>{localHealth.status === 'ok' ? 'All systems operational' : 'Degraded'}</Badge></dd>
            </Card>
          </div>
        </section>
      )}

      <section className={styles.section}>
        <h2 className={styles.sTitle}>Retrieval Modes</h2>
        <div className={styles.modeTable}>
          {[
            { mode:'hybrid',      desc:'BM25 + vector via RRF k=60. Best quality. Default.', best:'All queries' },
            { mode:'vector_only', desc:'Semantic similarity (cosine on embeddings).',         best:'Conceptual paraphrases' },
            { mode:'bm25_only',   desc:'PostgreSQL full-text search (ts_rank).',              best:'"Article 33", exact IDs' },
          ].map(r => (
            <div key={r.mode} className={styles.modeRow}>
              <code className={styles.modeCode}>{r.mode}</code>
              <span className={styles.modeDesc}>{r.desc}</span>
              <span className={styles.modeBest}>Best for: {r.best}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
```

### `src/pages/Search.jsx`

```jsx
import { useState } from 'react'
import { search } from '../api/search'
import SearchForm from '../components/search/SearchForm'
import AnswerBlock from '../components/search/AnswerBlock'
import CitationCard from '../components/search/CitationCard'
import ConfidenceGauge from '../components/search/ConfidenceGauge'
import MetaBar from '../components/search/MetaBar'
import GuardrailBanner from '../components/search/GuardrailBanner'
import FeedbackButtons from '../components/feedback/FeedbackButtons'
import Card from '../components/ui/Card'
import styles from './Search.module.css'

export default function Search({ config }) {
  const [result, setResult]   = useState(null)
  const [headers, setHeaders] = useState(null)
  const [lastParams, setParams] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  async function handleSearch(params) {
    setLoading(true); setError(null); setResult(null); setHeaders(null); setParams(params)
    try {
      const { data, headers: h } = await search(params)
      setResult(data); setHeaders(h)
    } catch(e) { setError(e) }
    finally { setLoading(false) }
  }

  function errMsg(e) {
    if (!e) return null
    if (e.status === 400) return { type: 'blocked', reason: e.body?.detail?.reason }
    if (e.status === 404) return { type: 'generic', message: 'No documents found in this namespace. Upload a document first.' }
    if (e.status === 429) {
      const isbudget = e.body?.error === 'daily_token_budget_exceeded'
      return { type: 'generic', message: isbudget ? `Daily token budget exceeded. Resets at midnight UTC.` : 'Rate limit reached. Try again in a moment.' }
    }
    if (e.status === 502) return { type: 'generic', message: 'AI provider temporarily unavailable.' }
    return { type: 'generic', message: e.message || 'Unexpected error.' }
  }

  const err = errMsg(error)
  const floor = config?.confidence_floor ?? 0.45

  return (
    <div className={styles.page}>
      <header className={styles.header}><h1>Search</h1><p>Ask a question — the platform retrieves relevant chunks and generates a cited answer.</p></header>
      <SearchForm onSubmit={handleSearch} loading={loading} config={config} />
      {err && (
        <div className={styles.errorSection}>
          {err.type === 'blocked'
            ? <GuardrailBanner type="blocked" reason={err.reason} />
            : <div className={styles.genericError} role="alert">⊘ {err.message}</div>}
        </div>
      )}
      {result && (
        <div className={styles.results} role="region" aria-label="Search results" aria-live="polite">
          {result.needs_clarification && <GuardrailBanner type="clarification" />}
          {result.flagged && <GuardrailBanner type="flagged" reason={result.flag_reason} confidence={result.confidence} floor={floor} />}

          {/* rerank_applied mismatch warning */}
          {result.rerank_applied === false && lastParams?.rerank === true && (
            <p className={styles.rerankNote}>ℹ Reranking was requested but is unavailable in this deployment mode.</p>
          )}

          <Card title="Answer" accent>
            <AnswerBlock answer={result.answer} />
            <FeedbackButtons requestId={headers?.queryId} endpoint="/search" />
          </Card>

          <div className={styles.metricsRow}>
            <Card><ConfidenceGauge confidence={result.confidence} floor={floor} /></Card>
            <Card><MetaBar headers={headers} /></Card>
          </div>

          {result.results?.length > 0 && (
            <section aria-label="Source citations">
              <h2 className={styles.citationsTitle}>Sources <span className={styles.citCount}>{result.total_results}</span></h2>
              <div className={styles.citList}>{result.results.map((r,i) => <CitationCard key={`${r.document_id}-${i}`} result={r} index={i} />)}</div>
            </section>
          )}
        </div>
      )}
      {!result && !error && !loading && (
        <div className={styles.empty} aria-hidden="true">
          <span className={styles.emptyIcon}>⌕</span>
          <p>Enter a query above to search your documents.</p>
        </div>
      )}
      {loading && (
        <div className={styles.loading} aria-busy="true" aria-label="Searching…">
          <div className={styles.loadingBar} />
          <p>Searching and generating answer…</p>
        </div>
      )}
    </div>
  )
}
```

### `src/pages/Agent.jsx`

```jsx
import { useState } from 'react'
import { agentQuery } from '../api/agent'
import AgentForm from '../components/agent/AgentForm'
import AgentCitationCard from '../components/agent/AgentCitationCard'
import AnswerBlock from '../components/search/AnswerBlock'
import ConfidenceGauge from '../components/search/ConfidenceGauge'
import GuardrailBanner from '../components/search/GuardrailBanner'
import MetaBar from '../components/search/MetaBar'
import VerificationBadge from '../components/agent/VerificationBadge'
import ReasoningChain from '../components/agent/ReasoningChain'
import FeedbackButtons from '../components/feedback/FeedbackButtons'
import Card from '../components/ui/Card'
import styles from './Agent.module.css'

export default function Agent({ config }) {
  const [result, setResult]   = useState(null)
  const [headers, setHeaders] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const floor = config?.confidence_floor ?? 0.45

  async function handleSubmit(params) {
    setLoading(true); setError(null); setResult(null); setHeaders(null)
    try {
      const { data, headers: h } = await agentQuery(params)
      setResult(data); setHeaders(h)
    } catch(e) { setError(e) }
    finally { setLoading(false) }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Agent</h1>
        <p>Multi-step reasoning with iterative retrieval and optional verification. Takes 8-15s for complex queries.</p>
      </header>
      <AgentForm onSubmit={handleSubmit} loading={loading} config={config} />
      {loading && (
        <div className={styles.loading} aria-busy="true">
          <div className={styles.loadingBar} />
          <p>Agent is researching… this may take several seconds.</p>
        </div>
      )}
      {error && <div className={styles.errorBanner} role="alert">⊘ {error.body?.detail || error.message}</div>}
      {result && (
        <div className={styles.results} role="region" aria-live="polite" aria-label="Agent response">
          <Card title="Answer" accent>
            <AnswerBlock answer={result.answer} />
            <FeedbackButtons requestId={headers?.queryId} endpoint="/agent/query" />
          </Card>
          <div className={styles.metricsRow}>
            <Card><ConfidenceGauge confidence={result.confidence} floor={floor} /></Card>
            <Card><VerificationBadge verified={result.verified} notes={result.verification_notes} /></Card>
            <Card>
              <MetaBar headers={headers} />
              <dl className={styles.agentStats}>
                <div><dt>Tool calls</dt><dd>{result.tool_calls_made}</dd></div>
                <div><dt>Time</dt><dd>{result.total_time_seconds.toFixed(2)}s</dd></div>
                <div><dt>Total cost</dt><dd>${result.total_cost_usd.toFixed(6)}</dd></div>
                <div><dt>Model</dt><dd className={styles.model}>{result.model_used?.split('/').pop()}</dd></div>
              </dl>
            </Card>
          </div>
          <ReasoningChain steps={result.reasoning_steps} toolCallCount={result.tool_calls_made} />
          {result.citations?.length > 0 && (
            <section>
              <h2 className={styles.citTitle}>Sources <span className={styles.citCount}>{result.citations.length}</span></h2>
              <div className={styles.citList}>{result.citations.map((c,i) => <AgentCitationCard key={`${c.document_id}-${i}`} citation={c} index={i} />)}</div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
```

### `src/pages/Ingest.jsx`

```jsx
import { useState } from 'react'
import { ingestFile } from '../api/ingest'
import DropZone from '../components/ingest/DropZone'
import IngestResult from '../components/ingest/IngestResult'
import styles from './Ingest.module.css'

export default function Ingest({ config }) {
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  async function handleUpload(params) {
    setLoading(true); setError(null); setResult(null)
    try { setResult(await ingestFile(params)) }
    catch(e) { setError(e) }
    finally { setLoading(false) }
  }

  function errMsg(e) {
    if (!e) return null
    if (e.status === 415) return 'Unsupported file type. Upload .txt, .md, or .pdf.'
    if (e.status === 429) return 'Rate limit reached. Wait before uploading again.'
    return e.message || 'Upload failed. Try again.'
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Ingest Documents</h1>
        <p>Upload documents to a namespace. The platform chunks, embeds, and indexes automatically. SHA-256 deduplication prevents re-processing identical files.</p>
      </header>
      <DropZone onUpload={handleUpload} loading={loading} config={config} />
      {error && <div className={styles.error} role="alert">⊘ {errMsg(error)}</div>}
      {result && <IngestResult result={result} />}
    </div>
  )
}
```

### `src/pages/Analytics.jsx`

```jsx
import { useState, useEffect } from 'react'
import { getAnalyticsSummary } from '../api/analytics'
import Card from '../components/ui/Card'
import styles from './Analytics.module.css'

const DAYS = [7, 14, 30, 90]

export default function Analytics() {
  const [days, setDays]         = useState(7)
  const [summary, setSummary]   = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)

  useEffect(() => {
    let gone = false
    setLoading(true); setError(null)
    getAnalyticsSummary(days)
      .then(d  => { if (!gone) setSummary(d) })
      .catch(e => { if (!gone) setError(e) })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [days])

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Analytics</h1>
        <div className={styles.dayPicker} role="group" aria-label="Time window">
          {DAYS.map(d => (
            <button key={d} className={`${styles.dayBtn} ${d === days ? styles.active : ''}`}
              onClick={() => setDays(d)} aria-pressed={d === days}>{d}d</button>
          ))}
        </div>
      </header>

      {loading && <p className={styles.info}>Loading analytics…</p>}
      {error && <p className={styles.err} role="alert">{error.message}</p>}

      {summary && (
        <>
          <div className={styles.summaryRow}>
            <Card><dt className={styles.dt}>Total cost</dt><dd className={styles.dd}>${summary.total_cost_usd.toFixed(4)}</dd></Card>
            <Card><dt className={styles.dt}>Total requests</dt><dd className={styles.dd}>{summary.total_requests.toLocaleString()}</dd></Card>
            <Card><dt className={styles.dt}>Avg cost / request</dt><dd className={styles.dd}>${summary.avg_cost_per_request.toFixed(6)}</dd></Card>
            <Card><dt className={styles.dt}>Total tokens</dt><dd className={styles.dd}>{summary.total_tokens.toLocaleString()}</dd></Card>
          </div>

          <div className={styles.breakdownGrid}>
            <Card title="By namespace">
              <ul className={styles.list}>
                {summary.by_namespace.map(r => (
                  <li key={r.namespace} className={styles.row}>
                    <span className={styles.key}>{r.namespace}</span>
                    <span className={styles.val}>${r.cost_usd.toFixed(4)} · {r.requests} req</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="By endpoint">
              <ul className={styles.list}>
                {summary.by_endpoint.map(r => (
                  <li key={r.endpoint} className={styles.row}>
                    <span className={styles.key}>{r.endpoint}</span>
                    <span className={styles.val}>${r.cost_usd.toFixed(4)} · {r.requests} req</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="By model">
              <ul className={styles.list}>
                {summary.by_model.map(r => (
                  <li key={r.model} className={styles.row}>
                    <span className={styles.key}>{r.model.split('/').pop()}</span>
                    <span className={styles.val}>${r.cost_usd.toFixed(4)} · {r.requests} req</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          {summary.by_day.length > 0 && (
            <Card title="Daily breakdown">
              <table className={styles.table}>
                <thead><tr><th>Date</th><th>Cost</th><th>Tokens</th><th>Requests</th></tr></thead>
                <tbody>
                  {summary.by_day.map(r => (
                    <tr key={r.date}>
                      <td>{r.date}</td>
                      <td>${r.cost_usd.toFixed(4)}</td>
                      <td>{r.tokens.toLocaleString()}</td>
                      <td>{r.requests}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
```

### `src/pages/Documents.jsx`

```jsx
import { useState, useEffect } from 'react'
import { listDocuments } from '../api/documents'
import Card from '../components/ui/Card'
import styles from './Documents.module.css'

export default function Documents({ config }) {
  const namespaces   = config?.namespaces ? Object.keys(config.namespaces) : []
  const [ns, setNs]           = useState('')
  const [docs, setDocs]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    let gone = false
    setLoading(true); setError(null)
    listDocuments(ns || undefined)
      .then(d  => { if (!gone) setDocs(d.documents) })
      .catch(e => { if (!gone) setError(e) })
      .finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [ns])

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Documents</h1>
        <select className={styles.select} value={ns} onChange={e => setNs(e.target.value)} aria-label="Filter by namespace">
          <option value="">All namespaces</option>
          {namespaces.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </header>

      {loading && <p className={styles.info}>Loading documents…</p>}
      {error && <p className={styles.err} role="alert">{error.message}</p>}

      {!loading && !error && (
        <Card>
          <table className={styles.table}>
            <thead>
              <tr><th>Document</th><th>Namespace</th><th>Chunks</th><th>SHA-256</th><th>Last ingested</th></tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <tr key={`${doc.document_id}-${doc.namespace}`}>
                  <td>{doc.source_filename ?? doc.document_id}</td>
                  <td>{doc.namespace}</td>
                  <td>{doc.chunk_count.toLocaleString()}</td>
                  <td className={styles.hash} title={doc.content_hash}>{doc.content_hash?.slice(0,10)}…</td>
                  <td>{doc.last_ingested_at ? new Date(doc.last_ingested_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {docs.length === 0 && (
            <p className={styles.empty}>No documents ingested{ns ? ` in "${ns}"` : ''}.</p>
          )}
        </Card>
      )}
    </div>
  )
}
```

---

## Part 19: Deployment

```dockerfile
# ui/Dockerfile.ui
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

```nginx
# ui/nginx.conf
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }
    location ~* \.(js|css|png|svg|ico|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**Dev:**

```bash
cd ui/
npm install
npm run dev
# → http://localhost:5173
# Vite proxy: /api/* → http://localhost:8000
```

---

## Part 20: Accessibility Checklist

| Requirement | Where implemented |
|---|---|
| `aria-live="polite"` on result regions | `Search.jsx`, `Agent.jsx` results div |
| `role="alert"` on errors | all error banners |
| `role="meter"` on gauge | `ConfidenceGauge.jsx` track div |
| `role="switch"` on toggles | `Toggle.jsx` button |
| `role="img"` on status dots | `StatusDot.jsx` |
| `role="status"` on MetaBar | `MetaBar.jsx` wrapper |
| `aria-busy="true"` on loading | Search, Agent loading containers |
| `aria-pressed` on feedback buttons | `FeedbackButtons.jsx` |
| `aria-pressed` on day-picker | `Analytics.jsx` day buttons |
| Keyboard: Ctrl+Enter to submit | `SearchForm.jsx` `handleKeyDown` |
| Contrast: amber #e8a020 on #0c0e16 | 7.2:1 (WCAG AAA) |
| Contrast: muted #8892a4 on #0c0e16 | 4.7:1 (WCAG AA) |
| `.sr-only` class for screen readers | `index.css`, used in Toggle |

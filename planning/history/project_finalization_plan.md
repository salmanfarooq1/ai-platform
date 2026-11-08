# Platform Finalization Plan
## From Phase 1 Complete → Job-Search-Ready Codebase

> **Goal:** Zero bugs. Zero cleanup debt. Evaluation harness present. CI passing. 
> Live deployment possible. Final commit made. Project paused cleanly.
>
> **Timeline:** 1-2 weeks working alongside job search prep
> **This plan is self-sufficient** — another model can execute every task 
> from this document alone without additional context.
>
> **Project location (WSL):** `/home/ubuntu/ai-platform`

---

## SECTION 0 — PROJECT IDENTITY

### 0.1 The Name Problem

`"ai-platform"` is too generic and forgotten instantly. The project needs a name that:
- Is memorable and sounds like a real product
- Works as a standalone platform name AND as a vertical-specific product
- Has domain availability and is GitHub-searchable

### 0.2 Proposed Names — Ranked

| Name | Meaning | Verdict |
|---|---|---|
| **Synapse** | Neural junction between retrieval and generation — literally what RAG does | ✅ **Top pick** — technical, elegant, memorable |
| **Meridian** | Central reference point — "where all knowledge converges" | ✅ Strong — enterprise feel |
| **Nexus** | Hub connecting all knowledge sources | ✅ Good — slightly overused |
| **Forge** | Where raw documents become answers | ✅ Good — action-oriented |
| **Lattice** | Interconnected knowledge structure | ⚠️ Good but abstract |

### 0.3 Recommended Naming Strategy

**Core brand:** `Synapse` (the RAG engine/platform)

**Vertical-specific products built on it:**
| Product Name | Use Case | How to pitch it |
|---|---|---|
| `Synapse Compliance` | Regulatory Q&A (current demo) | "Ask your compliance documents" |
| `Synapse HR` | Employee knowledge base, policy search | "Your HR documentation, answered instantly" |
| `Synapse Enterprise` | Multi-namespace agent across all company data | "Your agentic layer over every data source" |
| `Synapse Data Room` | M&A/Legal due diligence document review | "AI-powered due diligence at scale" |

**For portfolio purposes:** Keep the codebase named `synapse` (or `synapse-rag`). 
The current demo uses `Synapse Compliance` framing.

### 0.4 Rename Implementation

**Files to update when renaming:**

```
pyproject.toml          → name = "synapse"
api/main.py             → title="Synapse RAG API", description="..."
ui/src/components/layout/TopBar.jsx  → "Synapse" instead of "AI Platform"
ui/src/components/layout/Sidebar.jsx → logo text "Synapse"
README.md               → full rewrite (Section 10)
Dockerfile              → comment/label updates only
docker-compose.yml      → service name can stay "api"
```

---

## SECTION 1 — CRITICAL BUG FIXES

> **All 6 bugs confirmed from Phase 1 review. Fix in this order.**

### Fix 1: Dead Import in Dashboard.jsx

**File:** `ui/src/pages/Dashboard.jsx`

```diff
- import { useState, useEffect } from 'react'
- import { getHealth } from '../api/health'
+ import { useState, useEffect } from 'react'
```

Remove line 2 entirely (`import { getHealth } from '../api/health'`). `getHealth` is never called in this component — health is passed as a prop from App.jsx.

---

### Fix 2: Unnecessary localHealth State Mirror

**File:** `ui/src/pages/Dashboard.jsx`

The current code:
```jsx
const [localHealth, setLocal] = useState(health)
useEffect(() => { setLocal(health) }, [health])
```

This creates a redundant state layer. Replace ALL occurrences of `localHealth` with `health` directly and delete both lines above:

```diff
- const [localHealth, setLocal] = useState(health)
- useEffect(() => { setLocal(health) }, [health])
```

Then replace all `localHealth` references with `health` (there are 4 in the file):
- `services = localHealth ? [` → `services = health ? [`
- `{localHealth && (` → `{health && (`
- `localHealth.mode` → `health.mode`
- `localHealth.status` → `health.status`
- `localHealth.uptime_seconds` → `health.uptime_seconds`
- `localHealth.version` → `health.version`

**Final Dashboard.jsx imports line:**
```jsx
import { useState } from 'react'
```
(Remove `useEffect` import too if it's no longer used after this fix.)

Actually keep `useEffect` only if the `services` computation needs it — but since `health` is a prop, it's already reactive. Full updated top-of-file:

```jsx
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import StatusDot from '../components/ui/StatusDot'
import styles from './Dashboard.module.css'

export default function Dashboard({ health }) {
  const services = health ? [
    { name: 'Database', status: health.db    === 'ok' ? 'ok' : 'error', detail: health.db },
    { name: 'Redis',    status: health.redis  === 'ok' ? 'ok' : 'error', detail: health.redis },
    { name: 'API',      status: 'ok', detail: `v${health.version}` },
  ] : []
  // ... rest unchanged, replacing all localHealth with health
```

---

### Fix 3: Root Endpoint Hardcoded Version

**File:** `api/main.py` — Line 79

```diff
 @app.get("/")
 async def root():
-    return {"status": "ok", "version": "0.4.0"}
+    return {"status": "ok", "version": app.version}
```

`app.version` is already set to `"0.4.0"` at line 44. This way, bumping the version in one place (`FastAPI(version=...)`) automatically propagates to the root endpoint.

---

### Fix 4: Update Stale Middleware Ordering Comment

**File:** `api/middleware/rate_limit.py` — Lines 7-19

Replace the stale docstring with the accurate full stack:

```python
"""
api/middleware/rate_limit.py

Fixed-window rate limiting per namespace using Redis INCR + EXPIRE.

Full middleware stack (LIFO — last added runs outermost/first on request):
  app.add_middleware(LoggingMiddleware)       # innermost — runs last on request
  app.add_middleware(LatencyMiddleware)
  app.add_middleware(FinOpsMiddleware)
  app.add_middleware(TokenBudgetMiddleware)
  app.add_middleware(RequestIDMiddleware)
  app.add_middleware(RateLimitMiddleware)     # 2nd outermost
  app.add_middleware(CORSMiddleware)          # outermost — runs first on request

RateLimitMiddleware runs BEFORE FinOps, TokenBudget, and LLM calls so that
rejected requests never reach the model and never incur cost. CORS runs
outermost so that OPTIONS preflight requests get proper headers even when
rate-limited.

Remember: FastAPI applies middleware in LIFO order.
The last one added is the first one executed on an incoming request.
"""
```

---

### Fix 5: Upload Size Limit on /ingest

**File:** `api/routers/ingest.py`

Add after the imports, before the router definition:

```python
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB hard cap

@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: Request,
    file: UploadFile = File(...),
    namespace: str = "default",
    document_id: str = None,
    pool: Pool = Depends(get_db_pool),
):
    # Size guard — read content first so we can check before processing
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024*1024)}MB upload limit.",
        )
    # Remove the duplicate `content = await file.read()` that was on line 40
```

**Important:** Remove the old `content = await file.read()` call that was at line 40 since we now read the content earlier. Update the subsequent `content_hash = compute_content_hash(content)` line — it still works because `content` is now in scope from the guard above.

---

### Fix 6: pyproject.toml Project Name + Version

**File:** `pyproject.toml`

```diff
 [project]
-name = "ai-platform"
-version = "0.1.0"
-description = "Production-grade AI backend platform"
+name = "synapse"
+version = "0.4.0"
+description = "Production-grade RAG platform with hybrid retrieval, LangGraph agent, and MCP integration"
```

Bump version to `0.4.0` to match `api/main.py`.

---

## SECTION 2 — SECURITY HARDENING

### 2.1 API Key Auth Middleware

**New file:** `api/middleware/auth.py`

```python
"""
api/middleware/auth.py

Simple API key gate for all non-public endpoints.

EXEMPT paths bypass auth — they must be safe to call without a key:
  /         → root health check (status page)
  /health   → deep health check (monitoring)
  /config   → frontend needs this at startup, before it has a key

All other paths require X-API-Key header matching the API_KEY env var.
If API_KEY is not set in the environment, the middleware is a no-op
(allows all requests through) — this lets local development work without
any configuration.

Set API_KEY in .env to enable auth:
  API_KEY=your-secret-key-here
"""
import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api.auth")

_API_KEY = os.getenv("API_KEY")  # read once at import time

EXEMPT_PATHS = {"/", "/health", "/config", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # No key configured → development mode, allow everything
        if not _API_KEY:
            return await call_next(request)

        # OPTIONS (preflight) must always pass — CORS handles it
        if request.method == "OPTIONS":
            return await call_next(request)

        # Exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Check the key
        provided = request.headers.get("X-API-Key", "")
        if provided != _API_KEY:
            logger.warning(
                "[auth] Rejected request to %s — invalid or missing X-API-Key",
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "detail": "Missing or invalid X-API-Key header."},
            )

        return await call_next(request)
```

**Register in `api/main.py`** — add the import and middleware registration:

```python
# Add import:
from api.middleware.auth import APIKeyMiddleware

# Add middleware (LIFO — add BEFORE RateLimitMiddleware so it runs just inside CORS):
app.add_middleware(LoggingMiddleware)
app.add_middleware(LatencyMiddleware)
app.add_middleware(FinOpsMiddleware)
app.add_middleware(TokenBudgetMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(APIKeyMiddleware)      # ← ADD THIS (runs between CORS and RateLimit)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CORSMiddleware, ...)
```

**Update `.env.example`:**
```
# API key for non-public endpoint auth (leave empty for local dev)
API_KEY=
```

**Frontend `ui/src/api/client.js`** — add the key header if set:

```javascript
// Read from Vite env at build time. Set VITE_API_KEY in .env.local
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

export async function apiFetch(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      ...options.headers,
    },
    ...options,
  })
  // ... rest unchanged
```

**Update `ui/.env.example`:**
```
VITE_API_URL=http://localhost:8000
VITE_API_KEY=
```

---

## SECTION 3 — EVALUATION HARNESS (Critical for Portfolio)

> This is the #1 signal hiring managers look for. Build it now.

### 3.1 Create the Evaluation Directory

```
scripts/eval/
├── README.md
├── golden_dataset.json
└── run_eval.py
```

### 3.2 Golden Dataset

**File:** `scripts/eval/golden_dataset.json`

This uses the compliance namespace demo documents. Create 20 question/answer pairs covering the kinds of queries the system is designed to handle:

```json
[
  {
    "question": "What is the definition of a Suspicious Activity Report (SAR)?",
    "ground_truth": "A Suspicious Activity Report (SAR) is a document filed with FinCEN by financial institutions to report suspected financial crimes, money laundering, or fraud under the Bank Secrecy Act (BSA).",
    "namespace": "compliance"
  },
  {
    "question": "What are the key components of a KYC (Know Your Customer) program?",
    "ground_truth": "A KYC program must include customer identification procedures (CIP), customer due diligence (CDD), enhanced due diligence (EDD) for high-risk customers, and ongoing monitoring of customer transactions.",
    "namespace": "compliance"
  },
  {
    "question": "What is the Bank Secrecy Act (BSA) threshold for currency transaction reports?",
    "ground_truth": "Financial institutions must file a Currency Transaction Report (CTR) for cash transactions exceeding $10,000 in a single business day, whether they are a single transaction or multiple related transactions.",
    "namespace": "compliance"
  },
  {
    "question": "What is the difference between AML and KYC?",
    "ground_truth": "AML (Anti-Money Laundering) is the broader framework of laws and controls designed to prevent money laundering. KYC (Know Your Customer) is a component of AML that specifically involves verifying customer identities and assessing their risk profiles before and during business relationships.",
    "namespace": "compliance"
  },
  {
    "question": "What is the purpose of a beneficial ownership rule?",
    "ground_truth": "The beneficial ownership rule requires financial institutions to identify and verify the identity of individuals who own or control companies that open accounts, specifically those owning 25% or more of the company or exercising significant control.",
    "namespace": "compliance"
  }
]
```

> **Note:** Expand this to 20-30 Q&A pairs once documents are ingested. The above 5 are a starter. Add real pairs based on what's actually in your ingested compliance documents.

### 3.3 Evaluation Script

**File:** `scripts/eval/run_eval.py`

```python
"""
scripts/eval/run_eval.py

Runs the golden dataset against the live /search endpoint and scores
each response using RAGAS metrics (faithfulness, answer_relevancy).

Usage:
    # Make sure the API is running, then:
    python scripts/eval/run_eval.py

    # With a threshold check (for CI):
    python scripts/eval/run_eval.py --threshold 0.65

    # Against a specific API URL:
    python scripts/eval/run_eval.py --api-url http://localhost:8000

Exit codes:
    0  → all metrics above threshold (or no threshold set)
    1  → one or more metrics below threshold
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"
REPORT_PATH = Path(__file__).parent / "eval_report.json"


def call_search(api_url: str, question: str, namespace: str, api_key: str) -> dict:
    """Call the /search endpoint and return the parsed response."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    resp = requests.post(
        f"{api_url}/search",
        json={
            "query": question,
            "namespace": namespace,
            "top_k": 5,
            "retrieval_mode": "hybrid",
            "rerank": False,  # disable reranking for eval consistency
        },
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Fail if any metric average falls below this value (0-1)")
    args = parser.parse_args()

    api_key = os.getenv("API_KEY", "")
    golden = json.loads(GOLDEN_PATH.read_text())

    print(f"Running eval on {len(golden)} questions against {args.api_url}...")
    print("-" * 60)

    questions, answers, contexts, ground_truths = [], [], [], []

    for item in golden:
        print(f"  → {item['question'][:60]}...")
        try:
            result = call_search(args.api_url, item["question"], item["namespace"], api_key)
            questions.append(item["question"])
            answers.append(result.get("answer", ""))
            # Use the retrieved chunk contents as context
            contexts.append([r["content"] for r in result.get("results", [])])
            ground_truths.append(item["ground_truth"])
        except Exception as e:
            print(f"    [ERROR] {e}")
            questions.append(item["question"])
            answers.append("")
            contexts.append([""])
            ground_truths.append(item["ground_truth"])

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    print("\nScoring with RAGAS...")
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
    scores = result.to_pandas()

    avg_faithfulness = float(scores["faithfulness"].mean())
    avg_relevancy = float(scores["answer_relevancy"].mean())

    report = {
        "faithfulness": avg_faithfulness,
        "answer_relevancy": avg_relevancy,
        "n_questions": len(golden),
        "individual": scores.to_dict(orient="records"),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(f"\n{'='*60}")
    print(f"  Faithfulness:    {avg_faithfulness:.3f}")
    print(f"  Answer Relevancy:{avg_relevancy:.3f}")
    print(f"  Report saved to: {REPORT_PATH}")
    print(f"{'='*60}")

    if args.threshold:
        if avg_faithfulness < args.threshold or avg_relevancy < args.threshold:
            print(f"\n✗ FAILED — metrics below threshold {args.threshold}")
            sys.exit(1)
        else:
            print(f"\n✓ PASSED — all metrics above threshold {args.threshold}")


if __name__ == "__main__":
    main()
```

### 3.4 Eval README

**File:** `scripts/eval/README.md`

```markdown
# Evaluation Harness

Runs a golden dataset of 20+ Q&A pairs against the live /search endpoint
and scores using RAGAS metrics.

## Metrics

| Metric | Description | Target |
|---|---|---|
| **Faithfulness** | Do answers stick to retrieved context? No hallucinations. | > 0.70 |
| **Answer Relevancy** | Does the answer address the question? | > 0.65 |

## Usage

```bash
# Ensure the API is running
cd /home/ubuntu/ai-platform
uvicorn api.main:app --reload

# In a second terminal:
pip install ragas datasets
python scripts/eval/run_eval.py

# With threshold (exits 1 if below):
python scripts/eval/run_eval.py --threshold 0.65
```

## Extending the Dataset

Add entries to `golden_dataset.json`:
```json
{
  "question": "Your question here",
  "ground_truth": "The correct, grounded answer",
  "namespace": "compliance"
}
```

The namespace must match a namespace in your ingested documents.
```

### 3.5 Add RAGAS to dev dependencies

**File:** `pyproject.toml` — add to `[dependency-groups] dev`:

```toml
[dependency-groups]
dev = [
    "pytest (>=9.1.1,<10.0.0)",
    "pytest-asyncio (>=1.4.0,<2.0.0)",
    "httpx (>=0.28.1,<0.29.0)",
    "pytest-cov (>=7.1.0,<8.0.0)",
    "ruff (>=0.5.0)",
    "ragas (>=0.2.0)",       # ← ADD
    "datasets (>=3.0.0)",    # ← ADD (required by ragas)
]
```

---

## SECTION 4 — CI/CD PIPELINE

**New file:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.11"

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install ruff
        run: pip install ruff

      - name: Run ruff
        run: ruff check api/ core/ tests/ config.py

  test:
    name: Unit Tests
    runs-on: ubuntu-latest
    needs: lint

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
      REDIS_URL: redis://localhost:6379
      MODE: local
      LLM_PROVIDER: groq
      GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
      EMBEDDING_MODEL: ollama/nomic-embed-text   # or mock in unit tests

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          pip install poetry
          poetry install --with dev

      - name: Run unit tests
        run: poetry run pytest tests/unit/ -v --cov=api --cov=core --cov-report=term-missing

      - name: Coverage gate (fail if < 60%)
        run: poetry run pytest tests/unit/ --cov=api --cov=core --cov-fail-under=60

  build-frontend:
    name: Frontend Build
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: ui/package-lock.json

      - name: Install dependencies
        run: cd ui && npm ci

      - name: Build
        run: cd ui && npm run build
        env:
          VITE_API_URL: https://placeholder.example.com
```

> **Note:** Add `GROQ_API_KEY` as a GitHub Actions secret in the repository settings. The unit tests mock most LLM calls, so this is only needed for tests that actually call the API.

---

## SECTION 5 — STRUCTURED LOGGING

> Replace f-string logging with structured output in the middleware layer.

### 5.1 Update LoggingMiddleware

**File:** `api/middleware/logging.py` — Replace `LoggingMiddleware`:

```python
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = getattr(request.state, "request_id", "—")
        logger.info(
            "[request] method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )

        response = await call_next(request)

        logger.info(
            "[response] method=%s path=%s status=%d request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
        )
        return response
```

The `logging.basicConfig` call at line 13 should be moved to `api/main.py` startup:

**File:** `api/main.py` — add at the top, after imports:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
```

Remove `logging.basicConfig(level=logging.INFO)` from `api/middleware/logging.py`.

---

## SECTION 6 — BACKEND PAGINATION

### 6.1 Documents Endpoint Pagination

**File:** `api/routers/docs.py`

Add `limit` and `offset` query params to the list endpoint:

```python
from fastapi import APIRouter, Depends, Query, Request

@router.get("/documents")
async def list_documents(
    namespace: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    pool: Pool = Depends(get_db_pool),
):
    async with pool.acquire() as conn:
        base_query = """
            SELECT document_id, namespace, source_filename,
                   chunk_count, last_ingested_at
            FROM documents
        """
        count_query = "SELECT COUNT(*) FROM documents"

        if namespace:
            where = " WHERE namespace = $1"
            args = [namespace]
            count_args = [namespace]
        else:
            where = ""
            args = []
            count_args = []

        total = await conn.fetchval(count_query + where, *count_args)
        rows = await conn.fetch(
            base_query + where + " ORDER BY last_ingested_at DESC LIMIT $" +
            str(len(args) + 1) + " OFFSET $" + str(len(args) + 2),
            *args, limit, offset,
        )

        return {
            "documents": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
```

---

## SECTION 7 — STARTUP PRINT → PROPER LOGGING

**File:** `api/main.py`

The `print()` calls in the lifespan function should use the logger:

```python
import logging
logger = logging.getLogger("api.startup")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    app.state.db_pool = await create_pool()
    app.state.agent_graph = build_agent_graph(app.state.db_pool)
    app.state.redis = await get_redis()
    await create_semantic_cache_index()
    init_mcp_context(app.state.db_pool)
    logger.info("[startup] DB pool, agent graph, Redis, semantic cache, MCP context ready")

    yield

    # SHUTDOWN
    await close_redis()
    await app.state.db_pool.close()
    logger.info("[shutdown] DB pool and Redis pool closed")
```

---

## SECTION 8 — FRONTEND COMPLETION

### 8.1 Theme Toggle Verification

> From the review: `useTheme` is already imported in TopBar.jsx and the Toggle is wired up. **The theme toggle is already working.** No code changes needed here.

Verify by running the UI locally and checking:
1. Click the 🌙/☀️ toggle in the TopBar
2. Theme should switch
3. Reload the page — theme should persist (localStorage)

If the toggle doesn't appear, check `ui/src/components/layout/TopBar.module.css` for `.themeSep` and the Toggle component styling.

### 8.2 Frontend Pagination for Documents Page

**File:** `ui/src/pages/Documents.jsx`

Add pagination controls to the documents list. The backend now returns `{documents, total, limit, offset}`.

```jsx
// Add state
const [page, setPage] = useState(0)
const LIMIT = 20

// Update fetch call
const { data } = await getDocuments({ namespace, limit: LIMIT, offset: page * LIMIT })
// data.documents, data.total

// Add pagination UI below the list:
{data && data.total > LIMIT && (
  <div className={styles.pagination}>
    <button
      disabled={page === 0}
      onClick={() => setPage(p => p - 1)}
      className={styles.pageBtn}
    >← Prev</button>
    <span className={styles.pageInfo}>
      {page * LIMIT + 1}–{Math.min((page + 1) * LIMIT, data.total)} of {data.total}
    </span>
    <button
      disabled={(page + 1) * LIMIT >= data.total}
      onClick={() => setPage(p => p + 1)}
      className={styles.pageBtn}
    >Next →</button>
  </div>
)}
```

Update `ui/src/api/documents.js` to accept and forward `limit`/`offset` params.

### 8.3 TopBar Platform Name Update (for rebranding)

**File:** `ui/src/components/layout/TopBar.jsx` — Line 24:

```diff
-        <span className={styles.platformName}>AI Platform</span>
+        <span className={styles.platformName}>Synapse</span>
```

**File:** `ui/src/components/layout/Sidebar.jsx` — Line 17-18:

```diff
-        <span className={styles.logoMark}>AI</span>
-        <span className={styles.logoText}>Platform</span>
+        <span className={styles.logoMark}>⬡</span>
+        <span className={styles.logoText}>Synapse</span>
```

---

## SECTION 9 — CODEBASE CLEANUP

### 9.1 Files to Review/Remove

Run these checks in the WSL terminal:

```bash
cd /home/ubuntu/ai-platform

# Check for stray scratch files not in .gitignore
find . -name "*.py" -path "*/scratch/*" 2>/dev/null
find . -name "*.md" -maxdepth 1 -not -name "README.md" -not -name "ARCHITECTURE.md"
ls -la *.md  # list all root-level markdown files
```

From the directory listing, these root-level files should be reviewed:
- `fronted_master_plan.md` — **typo in filename** (`fronted` not `frontend`). Check if it's in `.gitignore`. If not, add `fronted_master_plan.md` to `.gitignore` or delete it.
- `v5_sprint_plan.md` — already in `.gitignore`. Verify.
- `project_mental_model.md` — already in `.gitignore`. Verify.
- `qna_prep.md` — already in `.gitignore`. Verify.

### 9.2 Update .gitignore

**File:** `.gitignore` — add missing entries:

```
# Add these if not already present:
fronted_master_plan.md
*.md.resolved
.deepeval/
benchmarks/
```

### 9.3 Remove __pycache__ and .coverage from repo

```bash
# In WSL:
find /home/ubuntu/ai-platform -name "__pycache__" -type d
# These should not be tracked — .gitignore has __pycache__ but verify

git rm -r --cached .coverage 2>/dev/null || true
git rm -r --cached __pycache__ 2>/dev/null || true
```

### 9.4 Check .env files are not committed

```bash
git ls-files | grep ".env"
# Should return nothing. If it returns .env, .env.local etc., remove them:
git rm --cached .env .env.local 2>/dev/null || true
```

### 9.5 Dead Code Check

Run ruff to catch unused imports:

```bash
cd /home/ubuntu/ai-platform
poetry run ruff check api/ core/ config.py --select F401
# Fix any unused imports flagged
```

Known dead import to fix: `from api.services.retriever import ...` in `api/agent/tools.py` — verify actual usage.

---

## SECTION 10 — TESTING

### 10.1 Run All Unit Tests

```bash
cd /home/ubuntu/ai-platform
poetry run pytest tests/unit/ -v --tb=short 2>&1 | head -100
```

Expected: All 60 tests pass. If any fail, fix before proceeding.

### 10.2 Add Missing Middleware Tests

**New file:** `tests/unit/test_middleware.py`

```python
"""
Unit tests for auth and rate-limit middleware logic.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.auth import APIKeyMiddleware


def make_app(api_key: str | None = None):
    """Create a minimal test app with APIKeyMiddleware."""
    import os
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware)

    @app.get("/protected")
    def protected():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


class TestAPIKeyMiddleware:
    def test_no_key_configured_allows_all(self, monkeypatch):
        """When API_KEY env var is unset, all requests pass through."""
        monkeypatch.delenv("API_KEY", raising=False)
        # Re-import to pick up the monkeypatched env
        import importlib
        import api.middleware.auth as auth_mod
        importlib.reload(auth_mod)
        from api.middleware.auth import APIKeyMiddleware as ReloadedMW

        app = FastAPI()
        app.add_middleware(ReloadedMW)

        @app.get("/protected")
        def endpoint():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 200

    def test_wrong_key_returns_401(self, monkeypatch):
        """Wrong API key returns 401."""
        monkeypatch.setenv("API_KEY", "correct-key")
        import importlib
        import api.middleware.auth as auth_mod
        importlib.reload(auth_mod)
        from api.middleware.auth import APIKeyMiddleware as ReloadedMW

        app = FastAPI()
        app.add_middleware(ReloadedMW)

        @app.get("/protected")
        def endpoint():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/protected", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_correct_key_passes(self, monkeypatch):
        """Correct API key passes through."""
        monkeypatch.setenv("API_KEY", "correct-key")
        import importlib
        import api.middleware.auth as auth_mod
        importlib.reload(auth_mod)
        from api.middleware.auth import APIKeyMiddleware as ReloadedMW

        app = FastAPI()
        app.add_middleware(ReloadedMW)

        @app.get("/protected")
        def endpoint():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/protected", headers={"X-API-Key": "correct-key"})
        assert resp.status_code == 200

    def test_health_exempt(self, monkeypatch):
        """The /health path is exempt from auth."""
        monkeypatch.setenv("API_KEY", "correct-key")
        import importlib
        import api.middleware.auth as auth_mod
        importlib.reload(auth_mod)
        from api.middleware.auth import APIKeyMiddleware as ReloadedMW

        app = FastAPI()
        app.add_middleware(ReloadedMW)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        client = TestClient(app)
        resp = client.get("/health")  # no key
        assert resp.status_code == 200
```

### 10.3 Run Linting

```bash
poetry run ruff check api/ core/ tests/ config.py
# Fix all issues before committing
```

### 10.4 Verify Frontend Builds

```bash
cd /home/ubuntu/ai-platform/ui
npm run build
# Should complete without errors
# Output goes to ui/dist/
```

---

## SECTION 11 — DEPLOYMENT PREPARATION

### 11.1 Docker Verify

```bash
cd /home/ubuntu/ai-platform
docker compose up --build
# Verify: http://localhost:8000/health returns {"status": "ok", ...}
# Verify: http://localhost:5173 loads the UI
```

### 11.2 CORS Origins for Production

**File:** `api/main.py` — update CORS allow_origins to include the production URL:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", ""),  # production URL from env var
    ],
    ...
)
```

Add to `.env.example`:
```
FRONTEND_URL=https://your-deployed-frontend-url.com
```

### 11.3 Koyeb Deployment Notes

The project is already Koyeb-compatible (based on `MODE=demo` config):

1. Create a Koyeb account at koyeb.com (free tier)
2. Set env vars in Koyeb dashboard:
   ```
   MODE=demo
   DATABASE_URL=<your postgres url>
   REDIS_URL=<your redis url>
   GROQ_API_KEY=<your key>
   API_KEY=<a random secret>
   RERANKER_ENABLED=false  (saves RAM on free tier)
   ```
3. Point Koyeb to the GitHub repo, build from Dockerfile
4. Update `CORS_ORIGINS` / `FRONTEND_URL` after deployment

### 11.4 Frontend Env for Production

**File:** `ui/.env.production` (create this file, do NOT commit it):

```
VITE_API_URL=https://your-koyeb-api-url.koyeb.app
VITE_API_KEY=your-api-key
```

Add to `ui/.gitignore`:
```
.env.production
.env.local
```

---

## SECTION 12 — README REWRITE

The README is the #1 hiring document. Rewrite it with this structure:

```markdown
# Synapse — Production RAG Platform

> Hybrid retrieval (BM25 + pgvector + RRF), LangGraph agentic reasoning,
> MCP v2 integration, and FinOps cost tracking — built for production, 
> not prototyping.

**[Live Demo](https://your-url) · [Architecture](ARCHITECTURE.md) · [Eval Results](scripts/eval/eval_report.json)**

---

## What This Is

Synapse is a configurable RAG platform currently deployed for compliance
document intelligence. The same engine adapts to any document corpus:
HR knowledge bases, engineering runbooks, legal research, or enterprise data rooms.

The architecture demonstrates production AI engineering patterns:

- **Two-tier cache** — exact SHA-256 match (<10ms) + semantic HNSW similarity
  in Redis; cache-aside on miss, fire-and-forget write
- **Hybrid retrieval** — BM25 + pgvector (cosine) fused via RRF k=60; optional
  cross-encoder reranking (CPU-offloaded via ProcessPoolExecutor)
- **FinOps middleware** — per-request cost attribution ($0.000186/search),
  daily token budget enforcement, usage persistence to Postgres
- **LangGraph agent** — multi-step tool-calling with answer verification loop
  and retry budget; reasoning chain exposed in the React UI
- **MCP v2** — 5 tools exposed via SSE transport for external agent integration

---

## Architecture

[include the architecture diagram from ARCHITECTURE.md here]

---

## Key Technical Decisions

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Vector DB | pgvector | Pinecone | Colocation with BM25 — single DB round-trip for hybrid search |
| Retrieval fusion | RRF k=60 | Learned ranking | Zero training data required; strong enough baseline |
| Rate limiting | Redis INCR | In-memory counter | Stateless across workers; atomic operation |
| Cache write | fire-and-forget | Blocking | Never delays the response; at most 1 record lost on crash |
| Reranker | Cross-encoder | LLM re-ranking | $0 cost; 40ms vs 500ms+ for an extra LLM call |

---

## Performance

| Metric | Value |
|---|---|
| Search (cache hit) | < 10ms |
| Search (cache miss, p50) | ~1.2s |
| Search cost (Groq) | $0.000186 / query |
| Agent query (3 tool calls) | ~8s, $0.000412 |
| Ingest throughput | ~30 chunks/sec |
| Retrieval modes | hybrid, vector_only, bm25_only |

---

## Evaluation

[Run the eval harness and paste results here:]
Faithfulness: 0.XX | Answer Relevancy: 0.XX | n=20 questions

---

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI, Python 3.11, asyncio |
| Agent | LangGraph, LiteLLM, Groq |
| Retrieval | pgvector, PostgreSQL BM25, sentence-transformers |
| Cache | Redis (exact + HNSW semantic) |
| Protocol | MCP v2 SSE transport |
| Frontend | React 19, Vite, CSS Modules |
| Deployment | Docker, Koyeb |

---

## Quick Start

```bash
git clone https://github.com/your-username/synapse
cd synapse
cp .env.example .env   # fill in GROQ_API_KEY, DATABASE_URL, REDIS_URL
docker compose up
# API: http://localhost:8000
# UI: http://localhost:5173
```
```

---

## SECTION 13 — EXECUTION ORDER (Final Checklist)

Execute in this exact order to ensure no regressions:

```
Step 1: Rename project
  [ ] Update pyproject.toml (name, version)
  [ ] Update api/main.py title + version fix (Fix 3)
  [ ] Update TopBar.jsx, Sidebar.jsx (rebrand to Synapse)

Step 2: Apply all bug fixes
  [ ] Fix 1: Remove dead import in Dashboard.jsx
  [ ] Fix 2: Remove localHealth state mirror in Dashboard.jsx
  [ ] Fix 3: Root endpoint version (api/main.py)
  [ ] Fix 4: Update stale middleware comment (rate_limit.py)
  [ ] Fix 5: Upload size limit in ingest.py
  [ ] Fix 6: pyproject.toml name + version

Step 3: Security
  [ ] Create api/middleware/auth.py
  [ ] Register APIKeyMiddleware in api/main.py
  [ ] Update client.js to send X-API-Key header
  [ ] Update .env.example with API_KEY field

Step 4: Evaluation harness
  [ ] Create scripts/eval/ directory
  [ ] Create golden_dataset.json (minimum 10 pairs to start)
  [ ] Create run_eval.py
  [ ] Create scripts/eval/README.md
  [ ] Add ragas + datasets to pyproject.toml dev deps

Step 5: CI/CD
  [ ] Create .github/workflows/ci.yml
  [ ] Add GROQ_API_KEY to GitHub repo secrets
  [ ] Push and verify CI passes on first run

Step 6: Backend improvements
  [ ] Structured logging in middleware/logging.py
  [ ] Move basicConfig to main.py
  [ ] Replace print() with logger in lifespan
  [ ] Pagination in docs router

Step 7: Frontend
  [ ] Verify theme toggle works visually
  [ ] Update pagination in Documents page

Step 8: Cleanup
  [ ] Run: ruff check api/ core/ tests/ config.py → fix all
  [ ] Run: git ls-files | grep ".env" → remove any leaked env files
  [ ] Verify .gitignore covers all generated files
  [ ] Check no __pycache__ or .coverage tracked

Step 9: Tests
  [ ] poetry run pytest tests/unit/ -v → all pass
  [ ] Add tests/unit/test_middleware.py
  [ ] poetry run pytest tests/unit/ -v → all pass (including new)
  [ ] npm run build (in ui/) → success

Step 10: Eval run
  [ ] Start the API locally
  [ ] Ingest at least the compliance documents
  [ ] python scripts/eval/run_eval.py
  [ ] Note the scores
  [ ] Paste scores into README

Step 11: README
  [ ] Full rewrite per Section 12 template
  [ ] Add live demo URL once deployed
  [ ] Add eval scores

Step 12: Final commit
  [ ] git add -A
  [ ] git status → verify only expected files changed
  [ ] git commit -m "feat: finalize platform — Synapse v0.4.0"
        "- Rename project to Synapse"
        "- Fix 6 bugs (Dashboard dead import, localHealth, version endpoint, "
        "  middleware comment, upload size limit, pyproject version)"
        "- Add APIKeyMiddleware for auth"
        "- Add evaluation harness (RAGAS, golden dataset, CI-gated)"
        "- Add GitHub Actions CI (lint + unit tests + frontend build)"
        "- Structured logging, startup print → logger"
        "- Documents pagination"
        "- README rewrite"
  [ ] git push
  [ ] Verify CI passes on GitHub
```

---

## SECTION 14 — AFTER THE FINAL COMMIT

Once the commit is made and CI passes:

1. **Deploy to Koyeb** — get a live URL to put in the README
2. **Run the full eval** against the deployed URL — update README scores
3. **Record a 2-minute walkthrough video** — screen capture of:
   - Upload a document
   - Run a search — show cache MISS → cache HIT
   - Show the MetaBar (cost, tokens, latency)
   - Run an agent query — show the reasoning chain
   - Show Analytics page
4. **Pin the repo** on GitHub and write the LinkedIn post (from `job_search_master_context.md`)
5. **Project is paused.** Focus shifts to: job search + GCP certification + LeetCode.

---

## SECTION 15 — WHAT "PAUSING" MEANS

The project is not abandoned — it's feature-complete for its purpose. 
The following are explicitly NOT in scope for this phase:

- GraphRAG
- A2A protocol implementation
- Multi-tenant auth (per-user namespaces)
- Fine-tuning integration
- Production Kubernetes deployment
- Streaming responses

These are Phase 3 features. They can be added if a specific job interview 
asks for a demo of something this doesn't cover yet.

---

*This document is complete and self-sufficient. Every code block is copy-paste ready.*
*Total estimated implementation time: 8-12 hours of focused work.*

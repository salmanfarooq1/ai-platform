# Week 11 Implementation Plan — MCP Server + Persistent Cost Tracking

> **Revised** — incorporates all observations from deep-dive review (OBS-02 through OBS-06).
> Validated against commit `97e1168` | All imports, function signatures, and schema fields checked against actual source.

---

## Revision Index

Changes made from the original plan:

| OBS | Change |
|---|---|
| OBS-02 | `FastMCP` → `MCPServer`, import path `from mcp.server import MCPServer` |
| OBS-03 | `server.py` split into `tools.py`, `resources.py`, `prompts.py` — `server.py` is registration only |
| OBS-04 | `get_ingestion_status` returns a Pydantic model instead of raw dict |
| OBS-05 | `app.router.routes.append(Mount(...))` → `app.mount(...)` for ASGI correctness |
| OBS-06 | `PRICING` dict moved out of `finops.py` into `config.py`; log message updated to point there; client configs extended to include Claude Desktop and Claude Code |

---

## Section A: Review Gap Fixes from Week 10

| # | Gap | Fix | File |
|---|---|---|---|
| G1 | No input guardrail on `/agent/query` — prompt injection sails through | Add `check_input()` before graph invocation | `api/agent/router.py` |
| G2 | `list_namespaces` is sync in async graph — blocks event loop briefly | Make it `async def` | `api/agent/tools.py` |
| G3 | Verifier instantiates fresh `ChatLiteLLM` per call — inconsistent with reasoning model pattern | Build once in `build_agent_graph`, pass via closure | `api/agent/graph.py` |

---

## Section B: MCP Server

### Task B1 — Install dependency

**File: `pyproject.toml`** — add to `dependencies`:

```
    "mcp (>=2.0.0,<3.0.0)",
```

Run `poetry add "mcp>=2.0.0,<3.0.0"` to resolve and lock.

---

### Task B2 — MCP package init

**New file: `api/mcp/__init__.py`**

```python
"""
api/mcp/
MCP (Model Context Protocol) server for the RAG platform.
Exposes retrieval, ingestion status, and compliance research
as MCP tools, resources, and prompts over SSE transport.
"""
```

---

### Task B3 — MCP tools

**New file: `api/mcp/tools.py`**

All five executable actions the MCP client can invoke. Each tool is a
standalone async function registered on the `mcp` instance imported from
`server.py`. Tools share the database pool via the app context dict that
is injected at startup.

```python
"""
MCP tool definitions.

Tools are executable functions an MCP client (Claude Desktop, Cursor,
VS Code) can invoke remotely. Each tool receives the database pool
through the server's context dependency dict, not through function
arguments, so the caller never has to know about connection management.
"""
import json
import logging
from typing import Any

from asyncpg import Pool

from api.mcp.server import mcp
from api.models.schemas import IngestionStatusResponse, LatestDocumentInfo
from api.services.cache import embed_query
from api.services.guardrails import check_input
from api.services.retriever import RetrieverConfig, retrieve
from config import FEATURES, NAMESPACE_REGISTRY

logger = logging.getLogger("api.mcp.tools")


@mcp.tool()
async def list_namespaces() -> str:
    """Return available document namespaces and what each contains.

    Call this before searching if you are not sure which namespace
    holds the regulation you need. The response is a JSON object
    mapping each namespace name to a description of its contents.
    """
    return json.dumps(NAMESPACE_REGISTRY, indent=2)


@mcp.tool()
async def search_documents(
    query: str,
    namespace: str = "default",
    top_k: int = 5,
    mode: str = "hybrid",
) -> str:
    """Search the compliance document database for chunks matching a query.

    Args:
        query: Natural language description of what you need.
        namespace: Document scope (use list_namespaces to discover).
        top_k: Number of results (1-20).
        mode: "hybrid" (default), "vector_only", or "bm25_only".

    Returns:
        JSON with matched chunks including content, scores, and metadata.
    """
    guard = check_input(query)
    if guard.blocked:
        return json.dumps({"error": "query_blocked", "reason": guard.blocked_reason})

    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    try:
        k = max(1, min(top_k, 20))
        query_embedding = await embed_query(query)
        cfg = RetrieverConfig(
            top_k=k,
            mode=mode,
            rerank=FEATURES.get("reranker_enabled", False),
        )
        chunks = await retrieve(
            pool=pool,
            query=query,
            query_embedding=query_embedding,
            namespace=namespace,
            cfg=cfg,
        )

        if not chunks:
            return json.dumps({"count": 0, "result": "No relevant chunks found"})

        results = []
        for i, c in enumerate(chunks):
            if "rrf_score" in c and c["rrf_score"] is not None:
                score = c["rrf_score"]
            elif "vector_score" in c and c["vector_score"] is not None:
                score = c["vector_score"]
            else:
                score = c.get("bm25_score", 0.0)

            results.append({
                "chunk_index": i,
                "document_id": c["document_id"],
                "source_filename": c.get("source_filename", "unknown"),
                "score": round(float(score), 4),
                "content": c["content"][:800],
            })

        return json.dumps({"count": len(results), "chunks": results}, indent=2)

    except Exception as e:
        logger.error("[mcp/search] %s", e)
        return json.dumps({"error": str(e)})


@mcp.tool()
async def multi_namespace_search(
    query: str,
    namespaces: list[str] | None = None,
    top_k: int = 3,
) -> str:
    """Search across multiple namespaces and merge results.

    Use this for cross-regulation comparisons like "Compare GDPR and
    CCPA breach notification timelines". Searches each namespace
    independently and returns combined results sorted by score.

    Args:
        query: Natural language question.
        namespaces: List of namespaces to search. Defaults to all known.
        top_k: Results per namespace (1-10).
    """
    targets = namespaces or list(NAMESPACE_REGISTRY.keys())
    all_results = []

    for ns in targets:
        raw = await search_documents(query=query, namespace=ns, top_k=top_k)
        data = json.loads(raw)
        for chunk in data.get("chunks", []):
            chunk["namespace"] = ns
            all_results.append(chunk)

    all_results.sort(key=lambda c: c.get("score", 0), reverse=True)
    return json.dumps({"count": len(all_results), "chunks": all_results}, indent=2)


@mcp.tool()
async def get_ingestion_status(
    namespace: str = "default",
) -> str:
    """Check how many documents and chunks exist in a namespace.

    Returns document count, total chunk count, and the most recently
    ingested document. Useful for verifying that a corpus has been
    loaded before running searches against it.
    """
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    try:
        async with pool.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT document_id) AS doc_count,
                    COUNT(*) AS chunk_count
                FROM documents
                WHERE namespace = $1
                """,
                namespace,
            )
            latest = await conn.fetchrow(
                """
                SELECT document_id, source_filename, last_ingested_at
                FROM document_registry
                WHERE namespace = $1
                ORDER BY last_ingested_at DESC
                LIMIT 1
                """,
                namespace,
            )

        latest_info: LatestDocumentInfo | None = None
        if latest:
            latest_info = LatestDocumentInfo(
                document_id=latest["document_id"],
                source_filename=latest["source_filename"],
                ingested_at=latest["last_ingested_at"].isoformat(),
            )

        result = IngestionStatusResponse(
            namespace=namespace,
            document_count=stats["doc_count"],
            chunk_count=stats["chunk_count"],
            latest_document=latest_info,
        )
        return result.model_dump_json(indent=2)

    except Exception as e:
        logger.error("[mcp/ingestion_status] %s", e)
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_cost_summary(
    days: int = 7,
) -> str:
    """Get LLM cost summary for recent days.

    Returns per-day breakdown of token usage and dollar cost.
    Useful for monitoring spend before it hits budget limits.

    Args:
        days: Number of days to look back (1-30, default 7).
    """
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    try:
        d = max(1, min(days, 30))
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    DATE(created_at) AS day,
                    endpoint,
                    SUM(prompt_tokens) AS total_prompt,
                    SUM(completion_tokens) AS total_completion,
                    SUM(cost_usd) AS total_cost,
                    COUNT(*) AS request_count
                FROM usage_log
                WHERE created_at >= NOW() - MAKE_INTERVAL(days => $1)
                GROUP BY DATE(created_at), endpoint
                ORDER BY day DESC, endpoint
                """,
                d,
            )

        result = [
            {
                "date": r["day"].isoformat(),
                "endpoint": r["endpoint"],
                "prompt_tokens": r["total_prompt"],
                "completion_tokens": r["total_completion"],
                "cost_usd": float(r["total_cost"]),
                "requests": r["request_count"],
            }
            for r in rows
        ]

        return json.dumps({"days": d, "breakdown": result}, indent=2)

    except Exception as e:
        logger.error("[mcp/cost_summary] %s", e)
        return json.dumps({"error": str(e)})
```

---

### Task B4 — MCP resources

**New file: `api/mcp/resources.py`**

Resources are read-only data an MCP client can pull into its context window
directly, without running a tool call. Think of them as remote files.

```python
"""
MCP resource definitions.

Resources expose read-only platform data to MCP clients.
Unlike tools, resources are passive — the client reads them like a file
rather than invoking them like a function.
"""
import json
import logging
from typing import Any

from asyncpg import Pool

from api.mcp.server import mcp
from config import FEATURES, NAMESPACE_REGISTRY

logger = logging.getLogger("api.mcp.resources")


@mcp.resource("rag://config/namespaces")
async def resource_namespaces() -> str:
    """Current namespace registry with descriptions."""
    return json.dumps(NAMESPACE_REGISTRY, indent=2)


@mcp.resource("rag://config/features")
async def resource_features() -> str:
    """Active feature flags for this deployment."""
    return json.dumps(FEATURES, indent=2)


@mcp.resource("rag://documents/{namespace}/{document_id}")
async def resource_document(namespace: str, document_id: str) -> str:
    """Full chunk listing for a specific ingested document."""
    ctx: dict[str, Any] = mcp._dependency_overrides.get("app_context", {})
    pool: Pool | None = ctx.get("pool")
    if pool is None:
        return json.dumps({"error": "Database pool not available"})

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, content, metadata
            FROM documents
            WHERE namespace = $1 AND document_id = $2
            ORDER BY id
            """,
            namespace, document_id,
        )

    chunks = [
        {"chunk_id": r["id"], "content": r["content"], "metadata": dict(r["metadata"] or {})}
        for r in rows
    ]
    return json.dumps({"document_id": document_id, "namespace": namespace, "chunks": chunks}, indent=2)
```

---

### Task B5 — MCP prompts

**New file: `api/mcp/prompts.py`**

Prompts are reusable workflow templates that appear as clickable buttons in
MCP clients like Claude Desktop. The user clicks a prompt, fills in a
parameter, and the pre-written instructions are sent directly to the LLM.

```python
"""
MCP prompt definitions.

Prompts are reusable workflow templates surfaced as clickable options in
MCP client interfaces. They guide the LLM through multi-step tasks by
providing step-by-step instructions as the initial message.
"""
from api.mcp.server import mcp


@mcp.prompt("compliance-research")
async def prompt_compliance_research(question: str, namespace: str = "legal") -> str:
    """Guided compliance research workflow.

    Generates a prompt that instructs the LLM to first check what
    namespaces are available, then search the right one, then
    synthesize a cited answer.
    """
    return (
        f"I need to research a compliance question: '{question}'\n\n"
        f"Please follow these steps:\n"
        f"1. Call list_namespaces to see what document scopes are available.\n"
        f"2. Search the '{namespace}' namespace (or whichever is most relevant) "
        f"using search_documents with the question.\n"
        f"3. If the question spans multiple regulations, use multi_namespace_search.\n"
        f"4. Synthesize a clear answer citing the specific chunks you found.\n"
        f"5. If you cannot find relevant context, say so explicitly."
    )


@mcp.prompt("cost-audit")
async def prompt_cost_audit(days: int = 30) -> str:
    """Cost audit workflow for reviewing LLM spend."""
    return (
        f"I need to audit LLM costs for the past {days} days.\n\n"
        f"1. Call get_cost_summary with days={days} to see per-day breakdown.\n"
        f"2. Identify which endpoints consume the most tokens.\n"
        f"3. Flag any days where cost_usd exceeds $1.00.\n"
        f"4. Suggest optimizations if agent queries dominate spend."
    )
```

---

### Task B6 — MCP server registration

**New file: `api/mcp/server.py`**

This file does one thing only: create the `MCPServer` instance. All tools,
resources, and prompts import this object and register themselves on it. This
keeps the server instantiation separate from the business logic.

```python
"""
MCP server instance.

Creates the central MCPServer object that all tools, resources, and
prompts register themselves onto. Import this module to access the
shared server instance. Do not define tools or resources here.
"""
from mcp.server import MCPServer

mcp = MCPServer(
    "RAG-Platform",
    instructions=(
        "Compliance document research server. Use search_documents for "
        "single-namespace queries and multi_namespace_search for cross-regulation "
        "comparisons. Call list_namespaces first if you are unsure which scope to use."
    ),
)
```

---

### Task B7 — SSE transport integration into FastAPI

**New file: `api/mcp/transport.py`**

```python
"""
SSE transport bridge between the MCP server and the FastAPI app.

MCP clients connect via two HTTP endpoints:
  GET  /mcp/sse        — opens a persistent Server-Sent Events stream
  POST /mcp/messages/  — sends JSON-RPC requests into the active session

The GET endpoint holds the connection open for the lifetime of the
MCP session. The POST endpoint routes incoming tool calls through
the SSE transport back to the MCP server's handler.

The app_context dict (containing the DB pool) is injected into
the MCP server's dependency overrides at startup so every tool
can access shared resources without global mutable state.
"""
import logging

from asyncpg import Pool
from fastapi import APIRouter, Request

from api.mcp.server import mcp

# Import modules so their decorators register on the mcp instance above.
import api.mcp.tools      # noqa: F401
import api.mcp.resources  # noqa: F401
import api.mcp.prompts    # noqa: F401

from mcp.server.sse import SseServerTransport

logger = logging.getLogger("api.mcp.transport")

router = APIRouter(prefix="/mcp", tags=["mcp"])
sse_transport = SseServerTransport("/mcp/messages/")


def init_mcp_context(pool: Pool) -> None:
    """Inject shared app resources into MCP server context.

    Called once during FastAPI lifespan startup, after the DB pool
    is created. Tools read from this dict via
    mcp._dependency_overrides["app_context"].
    """
    mcp._dependency_overrides["app_context"] = {"pool": pool}
    logger.info("[mcp] Context initialized with DB pool")


@router.get("/sse")
async def handle_sse(request: Request):
    """Open an SSE session for an MCP client.

    The connection stays alive until the client disconnects.
    Each session gets its own read/write stream pair. The MCP
    server processes tool calls, resource reads, and prompt
    requests through these streams.
    """
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),
        )
```

---

### Task B8 — Mount MCP into FastAPI app

**File: `api/main.py`** — the full updated file:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.agent.graph import build_agent_graph
from api.agent.router import router as agent_router
from api.mcp.transport import init_mcp_context, router as mcp_router, sse_transport
from api.middleware.finops import FinOpsMiddleware
from api.middleware.logging import LatencyMiddleware, LoggingMiddleware, RequestIDMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.token_budget import TokenBudgetMiddleware
from api.routers.health import router as health_router
from api.routers.ingest import router as ingest_router
from api.routers.search import router as search_router
from api.services.cache import close_redis, create_semantic_cache_index, get_redis
from core.database.pool import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    app.state.db_pool = await create_pool()
    app.state.agent_graph = build_agent_graph(app.state.db_pool)
    app.state.redis = await get_redis()
    await create_semantic_cache_index()
    init_mcp_context(app.state.db_pool)
    print("[startup] DB pool, agent graph, Redis, semantic cache, MCP context ready")

    yield

    # SHUTDOWN
    await close_redis()
    await app.state.db_pool.close()
    print("[shutdown] DB pool and Redis pool closed")


app = FastAPI(
    title="RAG Platform API",
    version="0.4.0",
    lifespan=lifespan,
)

# MIDDLEWARE — LIFO order: last added = first executed
app.add_middleware(LoggingMiddleware)
app.add_middleware(LatencyMiddleware)
app.add_middleware(FinOpsMiddleware)
app.add_middleware(TokenBudgetMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.get("/")
async def root():
    return {"status": "ok", "version": "0.4.0"}


app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(search_router)
app.include_router(agent_router)
app.include_router(mcp_router)

# SseServerTransport.handle_post_message is a raw ASGI app, not a FastAPI
# endpoint function. It must be mounted directly, not registered as an
# APIRouter route. app.mount() hands the matching requests directly to the
# ASGI callable, bypassing FastAPI's request/response lifecycle entirely.
app.mount("/mcp/messages", sse_transport.handle_post_message)
```

---

### Task B9 — Pydantic schemas for MCP tool responses

**File: `api/models/schemas.py`** — append these two models:

```python
class LatestDocumentInfo(BaseModel):
    document_id: str
    source_filename: str
    ingested_at: str


class IngestionStatusResponse(BaseModel):
    namespace: str
    document_count: int
    chunk_count: int
    latest_document: LatestDocumentInfo | None = None
```

---

### Task B10 — MCP tests

**New file: `tests/unit/test_mcp_tools.py`**

```python
"""Unit tests for MCP server tools."""
import json

import pytest

from api.mcp.server import mcp


def test_mcp_server_has_name():
    assert mcp.name == "RAG-Platform"


@pytest.mark.asyncio
async def test_list_namespaces_tool():
    from api.mcp.tools import list_namespaces
    result = await list_namespaces()
    data = json.loads(result)
    assert "legal" in data
    assert "kyc_aml" in data
    assert "default" in data


@pytest.mark.asyncio
async def test_search_documents_missing_pool():
    """Without a DB pool in context, tools return a clean JSON error."""
    from api.mcp.tools import search_documents
    mcp._dependency_overrides.pop("app_context", None)
    result = await search_documents(query="test", namespace="default")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_search_documents_blocked_query():
    """Input guardrails apply to MCP tools, not just HTTP routes."""
    from api.mcp.tools import search_documents
    long_query = "x" * 2000
    result = await search_documents(query=long_query, namespace="default")
    data = json.loads(result)
    assert data.get("error") == "query_blocked"


@pytest.mark.asyncio
async def test_get_ingestion_status_missing_pool():
    from api.mcp.tools import get_ingestion_status
    mcp._dependency_overrides.pop("app_context", None)
    result = await get_ingestion_status(namespace="default")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_get_cost_summary_clamps_days():
    from api.mcp.tools import get_cost_summary
    mcp._dependency_overrides["app_context"] = {"pool": None}
    result = await get_cost_summary(days=100)
    data = json.loads(result)
    assert "error" in data


def test_multi_namespace_defaults_to_all():
    """multi_namespace_search with no explicit list should use all known namespaces."""
    from config import NAMESPACE_REGISTRY
    assert len(NAMESPACE_REGISTRY) >= 3
```

---

### Task B11 — Client configuration files

**New file: `.cursor/mcp.json`**

```json
{
  "mcpServers": {
    "rag-platform": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

**New file: `.vscode/mcp.json`**

```json
{
  "mcpServers": {
    "rag-platform": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

**New file: `claude_desktop_config.json`** (copy to `~/Library/Application Support/Claude/` on Mac or `%APPDATA%\Claude\` on Windows):

```json
{
  "mcpServers": {
    "rag-platform": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

**Claude Code (CLI)** — run once in terminal:

```bash
claude mcp add rag-platform --transport sse http://localhost:8000/mcp/sse
```

---

## Section C: Persistent Cost Tracking

### Task C1 — Centralize pricing configuration

**File: `core/config.py`** — append:

```python
# LLM token pricing in USD per million tokens.
# Update this dict when providers change rates, or replace with
# a dynamic fetch script (see OBS-06 in notes_and_obs.md).
MODEL_PRICING: dict[str, dict[str, float]] = {
    "azure/gpt-4o":                                        {"input": 2.50,  "output": 10.00},
    "groq/llama-3.1-70b-versatile":                        {"input": 0.59,  "output": 0.79},
    "groq/meta-llama/llama-4-scout-17b-16e-instruct":      {"input": 0.11,  "output": 0.34},
    "groq/meta-llama/llama-4-maverick-17b-128e-instruct":  {"input": 0.20,  "output": 0.60},
}
```

---

### Task C2 — Schema migration

**File: `core/database/schema.sql`** — append at end:

```sql
-- Per-request LLM usage log for cost tracking and monthly aggregation.
-- One row per API request that consumed LLM tokens.
-- FinOps middleware writes here after every /search and /agent/query response.
CREATE TABLE IF NOT EXISTS usage_log (
    id                BIGSERIAL PRIMARY KEY,
    request_id        VARCHAR(64)   NOT NULL,
    endpoint          VARCHAR(100)  NOT NULL,
    namespace         VARCHAR(255)  NOT NULL DEFAULT 'global',
    model             VARCHAR(200)  NOT NULL,
    prompt_tokens     INTEGER       NOT NULL DEFAULT 0,
    completion_tokens INTEGER       NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(12,8) NOT NULL DEFAULT 0.0,
    routing_decision  VARCHAR(50),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_log_created
    ON usage_log(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_usage_log_endpoint_date
    ON usage_log(endpoint, DATE(created_at));
```

---

### Task C3 — Usage writer service

**New file: `api/services/usage.py`**

```python
"""
Async usage log writer.

Provides a single function that the FinOps middleware calls to persist
one usage row per request. The write is fire-and-forget (errors are
logged, never raised) so a Postgres hiccup cannot crash or slow down
a user-facing response.
"""
import logging

from asyncpg import Pool

logger = logging.getLogger("api.usage")


async def record_usage(
    pool: Pool,
    request_id: str,
    endpoint: str,
    namespace: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    routing_decision: str = "",
) -> None:
    """Insert one usage row. Errors are swallowed and logged."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usage_log
                    (request_id, endpoint, namespace, model,
                     prompt_tokens, completion_tokens, cost_usd,
                     routing_decision)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                request_id,
                endpoint,
                namespace,
                model,
                prompt_tokens,
                completion_tokens,
                cost_usd,
                routing_decision,
            )
    except Exception as e:
        logger.warning("[usage] Failed to persist usage row: %s", e)
```

---

### Task C4 — Update FinOps middleware

**File: `api/middleware/finops.py`** — full replacement.

`PRICING` is now imported from `config.py`. The warning message now points
there too.

```python
"""
FinOps middleware — cost calculation and persistent usage logging.

Runs after the route handler returns. Reads request.state.usage
(set by /search and /agent/query routes), calculates dollar cost
from MODEL_PRICING in config.py, stamps response headers, and persists
the record to Postgres via the usage writer service.

The DB write is fire-and-forget: if Postgres is temporarily unreachable,
the header is still stamped and the request still succeeds.
"""
import asyncio
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from api.services.usage import record_usage
from config import MODEL_PRICING

logger = logging.getLogger("api.finops")


class FinOpsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        usage = getattr(request.state, "usage", None)
        cost_usd = 0.0

        if usage:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            model = usage.get("model", "unknown")

            if model.startswith("ollama/"):
                rates = {"input": 0.0, "output": 0.0}
            elif model not in MODEL_PRICING:
                logger.warning(
                    "[finops] Unknown model '%s' not in MODEL_PRICING. "
                    "Cost reported as $0.00. Add an entry to config.py.",
                    model,
                )
                rates = {"input": 0.0, "output": 0.0}
            else:
                rates = MODEL_PRICING[model]

            input_cost = (prompt_tokens / 1_000_000) * rates["input"]
            output_cost = (completion_tokens / 1_000_000) * rates["output"]
            cost_usd = input_cost + output_cost

        response.headers["X-Cost-USD"] = f"{cost_usd:.6f}"

        if usage:
            response.headers["X-Tokens-In"] = str(usage.get("prompt_tokens", 0))
            response.headers["X-Tokens-Out"] = str(usage.get("completion_tokens", 0))

            request_id = str(getattr(request.state, "request_id", "unknown"))
            response.headers["X-Query-ID"] = request_id

            logger.info(
                "[finops] %s cost=$%.6f model=%s tokens=%d+%d",
                request_id,
                cost_usd,
                usage.get("model", "unknown"),
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

            pool = getattr(request.app.state, "db_pool", None)
            if pool:
                asyncio.create_task(
                    record_usage(
                        pool=pool,
                        request_id=request_id,
                        endpoint=request.url.path,
                        namespace=usage.get("namespace", "global"),
                        model=usage.get("model", "unknown"),
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        cost_usd=cost_usd,
                        routing_decision=usage.get("routing_decision", ""),
                    )
                )

        return response
```

---

### Task C5 — Usage tracking tests

**New file: `tests/unit/test_usage.py`**

```python
"""Tests for usage persistence service."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_record_usage_swallows_db_errors():
    """A Postgres failure must not propagate — it is fire-and-forget."""
    from api.services.usage import record_usage

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
    mock_pool.acquire = MagicMock(return_value=_async_cm(mock_conn))

    await record_usage(
        pool=mock_pool,
        request_id="test-123",
        endpoint="/search",
        namespace="legal",
        model="groq/meta-llama/llama-4-scout-17b-16e-instruct",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.00003,
    )


class _async_cm:
    """Minimal async context manager wrapper for mock connections."""
    def __init__(self, obj):
        self._obj = obj
    async def __aenter__(self):
        return self._obj
    async def __aexit__(self, *args):
        pass
```

---

## Section D: Gap Fixes

### Task D1 — Add guardrail to agent route

**File: `api/agent/router.py`** — add import at top:

```python
from api.services.guardrails import check_input
```

Inside `agent_query()`, add before graph invocation (after `start = time.perf_counter()`):

```python
    guard = check_input(payload.question)
    if guard.blocked:
        raise HTTPException(
            status_code=400,
            detail={"error": "query_blocked", "reason": guard.blocked_reason},
        )
```

---

### Task D2 — Make `list_namespaces` async in agent tools

**File: `api/agent/tools.py`** — change line 16 from `def` to `async def`:

```python
@tool
async def list_namespaces() -> str:
```

---

### Task D3 — Build verifier model once in graph constructor

**File: `api/agent/graph.py`** — in `build_agent_graph()`, construct the verifier model alongside the reasoning model:

```python
def build_agent_graph(pool: Pool):
    tools = [make_retrieve_tool(pool), list_namespaces]
    reasoning_model = ChatLiteLLM(
        model=LLM_CONFIG["model"],
        temperature=0,
        max_tokens=4000,
    ).bind_tools(tools)

    verifier_model = ChatLiteLLM(
        model=LLM_CONFIG["model"],
        temperature=0,
        max_tokens=500,
    )

    async def agent_node(state: AgentState) -> dict:
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]]
        response = await reasoning_model.ainvoke(messages)
        return {
            "messages": [response],
            "reasoning_usage": [_extract_llm_usage(response)],
        }

    async def verify_node_inner(state: AgentState) -> dict:
        chunks = _extract_chunks(state["messages"])
        excerpts = "\n\n".join(
            f"[{c.get('document_id')}] {c.get('content', '')[:500]}" for c in chunks
        )
        response = await verifier_model.ainvoke([
            SystemMessage(content=VERIFIER_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Draft answer:\n{state['final_answer']}\n\nSource chunks:\n{excerpts}"
            ),
        ])

        try:
            parsed = json.loads(response.content)
            supported = bool(parsed.get("supported", True))
            notes = parsed.get("notes", "")
        except (json.JSONDecodeError, TypeError):
            supported = True
            notes = "Verifier response was not valid JSON; treated as supported."

        update = {
            "verified": supported,
            "verification_notes": notes,
            "verifier_usage": [_extract_llm_usage(response)],
        }

        retries_left = state.get("verify_retries_left", 0)
        if not supported and retries_left > 0:
            update["verify_retries_left"] = retries_left - 1
            update["messages"] = [HumanMessage(
                content=f"[Verifier feedback] {notes} Please retrieve additional context to address this."
            )]

        return update

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("verify", verify_node_inner)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "synthesize": "synthesize"})
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("synthesize", should_verify, {"verify": "verify", "end": END})
    graph.add_conditional_edges("verify", verify_router, {"retry": "agent", "end": END})

    return graph.compile()
```

---

### Task D4 — Documentation update

**File: `ARCHITECTURE.md`** — add Decision 17:

```markdown
## Decision 17: MCP server over SSE transport, mounted into existing FastAPI app (Week 11)
**Context:** The platform exposes capabilities through REST routes (`/search`, `/agent/query`), but MCP-compatible AI tools (Claude Desktop, Cursor, VS Code Copilot) expect a Model Context Protocol server to discover and invoke tools programmatically. Building a separate MCP microservice would duplicate the retrieval stack.
**Decision:** Mount an MCP server (using the `mcp` Python SDK's `MCPServer` class) into the existing FastAPI app. SSE transport serves two endpoints: `GET /mcp/sse` for the event stream and `POST /mcp/messages/` for JSON-RPC requests. Tools delegate to the same `retrieve()`, `embed_query()`, and `check_input()` functions the REST routes use. The DB pool is injected via a context dict at startup, not through a global. Business logic is split into separate `tools.py`, `resources.py`, and `prompts.py` modules; `server.py` only holds the server instance.
**Why SSE, not stdio:** stdio requires the MCP server to run as a subprocess of the client. Our server already runs as an HTTP service on Koyeb. SSE lets any remote MCP client connect to the same deployed instance.
**Trade-off:** SSE connections are long-lived. Each connected MCP client holds one open HTTP connection for the session duration. On Koyeb's free tier with limited concurrent connections, this means practical concurrency is limited. Acceptable for development and single-user demo deployments. For multi-user production, Streamable HTTP transport (single-POST, no persistent connection) would replace SSE.
```

**Add Decision 18:**

```markdown
## Decision 18: Persistent cost tracking in Postgres via fire-and-forget writes (Week 11)
**Context:** FinOps middleware computed per-request cost but only stamped it in response headers and logged it to stdout. Token budget middleware tracked daily totals in Redis but keys expired after 25 hours. Neither provided historical cost data for monthly reporting.
**Decision:** A `usage_log` table in Postgres stores one row per LLM-consuming request. FinOps middleware writes to it via `asyncio.create_task` (fire-and-forget) so a Postgres failure cannot slow down or crash a user-facing response. The MCP `get_cost_summary` tool queries this table for per-day breakdowns. Monthly aggregation is a standard SQL GROUP BY. The `MODEL_PRICING` dictionary is centralized in `config.py` so it is not buried inside middleware.
**Why fire-and-forget, not synchronous INSERT:** A synchronous write would add ~2ms latency to every response and, worse, would crash the response if Postgres is temporarily unreachable. Cost tracking is important but not as important as serving the response.
**Trade-off:** If the app crashes between creating the task and executing the INSERT, that one row is lost. At the scale this platform operates (hundreds, not millions, of requests per day), a missed row is negligible for monthly reports.
```

---

## Section E: Git Commits

```
fix(agent): add input guardrail to /agent/query
fix(agent): make list_namespaces async, build verifier model once in graph constructor
feat(config): centralize MODEL_PRICING dict in config.py
feat(schema): add usage_log table for persistent cost tracking
feat(schema): add IngestionStatusResponse and LatestDocumentInfo Pydantic models
feat(services): add fire-and-forget usage writer
feat(finops): import pricing from config, persist per-request usage to Postgres
feat(mcp): add MCPServer instance (server.py)
feat(mcp): add tools module (tools.py)
feat(mcp): add resources module (resources.py)
feat(mcp): add prompts module (prompts.py)
feat(mcp): add SSE transport, mount into FastAPI with app.mount
feat(mcp): add client configs for Cursor, VS Code, Claude Desktop, Claude Code
test(mcp): add tool unit tests
test(usage): add persistence error-swallowing test
docs: ARCHITECTURE.md decisions 17-18
```

---

## Verification Plan

### Automated tests
```bash
pytest tests/unit/test_mcp_tools.py tests/unit/test_usage.py -v
pytest tests/unit/test_agent_tools.py -v
```

### Manual verification
1. Start the app: `uvicorn api.main:app --reload`
2. Verify SSE endpoint stays open: `curl -N http://localhost:8000/mcp/sse`
3. Verify `/agent/query` rejects long queries: send a 2000-char query, expect 400
4. Run schema migration: `psql -f core/database/schema.sql`
5. Make a `/search` query, then run `SELECT * FROM usage_log` — expect one row
6. Add the Cursor config and verify the MCP server appears in Cursor's tool list

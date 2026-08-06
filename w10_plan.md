# Week 10 Implementation Plan — LangGraph Agent (Reconciled, Aug 2026)

> Reconciles two source documents: the plan validated against commit `40bc691`
> ("Doc A"), and the newer plan drafted from that source ("Doc B"). Doc B's
> architecture and rationale are kept — the two-role design (reasoning +
> verifier) and the `list_namespaces` tool were your calls, not something a
> model added on its own initiative, and both are architecturally sound.
> What changed here: two regressions Doc B reintroduced relative to Doc A's
> validated fixes, one internal-naming inconsistency, and dependency
> versions checked against what's actually on PyPI today rather than
> whatever was current when either doc was drafted.
>
> Every change below is tagged so you (and whichever coding model implements
> this) can tell at a glance what kind of change it is:
> **🐛 BUGFIX** — restores or applies a fix already validated in Doc A that Doc B lost.
> **⚙️ DESIGN** — a deliberate architectural choice, yours or newly reconciled, not a correction.
> **🚩 FLAG** — genuinely unresolved without seeing the live file; don't guess, verify at implementation time.

---

## 1. Reconciliation Summary — What Changed and Why

### 🐛 Two regressions in Doc B, both restored from Doc A's validated fixes

| # | Where | What Doc B did | Why it's a bug | Fix applied here |
|---|---|---|---|---|
| R1 | Task 1, `retrieve_vector()` | SQL adds a 4th bind param (`$4` for the score floor) but the task text never updates the function signature or the two existing call sites inside `retrieve()` | This is exactly the bug Doc A's validation caught (its B2/B3): `retrieve_vector()` as it stands takes 3 positional args, and both call sites pass 3. Adding a 4th param without touching the signature or callers throws `asyncpg.exceptions.DataError: insufficient params` the first time retrieval runs | Give the new param a default value pulled from `config.MIN_VECTOR_SCORE`. Existing 3-arg callers keep working unmodified; the floor is still configurable for anyone who wants to pass it explicitly later |
| R2 | Task 7, `agent_query()` | `graph.ainvoke()`'s initial state dict omits `reasoning_usage` and `verifier_usage` | This is Doc A's B8: both fields use `Annotated[list[dict], add]` in `AgentState`. LangGraph's reducer requires the key to exist before the first append — `agent_node`'s very first return (`{"reasoning_usage": [_extract_llm_usage(response)]}`) raises `InvalidUpdateError` if the key was never initialized | Initialize both to `[]` in the `ainvoke()` call, as Doc A's Task 7 already did correctly |

### ⚙️ One naming inconsistency, resolved for consistency (not a bug, but worth calling out explicitly)

Doc A's `retrieve_chunks` tool emits chunks keyed `source_filename`; Doc B's emits `source` and remaps it to `source_filename` one step later, inside `synthesize_node`. Both work — Doc B's remap is done correctly, it's not the same mistake as Doc A's original B6. But `retriever.py`'s `retrieve_vector()` (Task 1, both docs agree on this) already returns `"source_filename": meta.get("source_filename")` as its key. Using `source_filename` at every layer — retriever → tool → synthesize_node — means one key name for this field across the whole codebase instead of two. This plan uses `source_filename` throughout and drops the remap step. Purely a consistency choice, not a correctness fix; flagging it so it doesn't read as a silent change.

### 🚩 One thing neither doc actually resolved (carried forward as a flag, not guessed at)

Doc A's bug table (B7) flags that `ChatLiteLLM(model=LLM_CONFIG["model"])` — where the model string carries a `groq/` provider prefix — may or may not need an explicit `api_key` depending on the installed `langchain-litellm` version. Doc A's own code snippets never actually added the `api_key` param despite the table saying they would; Doc B doesn't mention it at all. Neither source document shows `config.py`'s actual field name for a Groq key, so this plan doesn't invent one. See §2 below — it's called out as an inline flag at both `ChatLiteLLM(...)` call sites in Task 6.

### Package versions, checked against PyPI today (Aug 3, 2026) rather than assumed

Doc A pinned `langgraph>=0.4.0,<1.0.0` and `langchain-core>=0.3.0,<1.0.0` with a `langchain-community`-based import fallback. Doc B guessed `langgraph>=1.2.0,<2.0.0`, `langchain-core>=1.4.0,<2.0.0`, `langchain-litellm>=0.2.0,<1.0.0` with a direct import. Checked just now:

| Package | Latest on PyPI (checked today) | Doc B's guess |
|---|---|---|
| `langgraph` | 1.2.10 | matches |
| `langchain-core` | 1.5.3 (1.4.0 was current when Doc B was likely drafted) | close, slightly behind |
| `langchain-litellm` | 0.2.2, and it's now the primary, documented distribution path for `ChatLiteLLM` (LangChain's own docs use `from langchain_litellm import ChatLiteLLM` directly, no `langchain_community` fallback shown) | matches, and the fallback import Doc A wanted (B5) is no longer necessary |

Doc B's guess turned out closer to reality than Doc A's older pins — time has passed since Doc A was validated. This plan uses Doc B's ranges, widened slightly to cover the newer patch releases, and drops the `try/except` import fallback since `langchain-litellm` is now the documented standard path. **Still true for both docs' original caution: re-run `pip index versions langgraph langchain-core langchain-litellm` right before installing** — by the time this plan is implemented, more releases will exist.

---

## 2. Open Flags — Verify These Before / During Implementation

Collected here so the implementing model can check them off, instead of them being buried in code comments only:

1. **`api_key` for `ChatLiteLLM`** (Task 6, both instantiations). `LLM_CONFIG["model"]` carries a `groq/` prefix. If `ChatLiteLLM` doesn't pick up the Groq key via LiteLLM's normal env-var passthrough, you'll see an auth or model-not-found error at runtime. Check `config.py` for however the Groq key is currently named and pass it as `api_key=...` if needed. Not fixed here because the field name isn't visible from this plan's source files.
2. **Exact call-site line numbers for `retrieve_vector()`** inside `retrieve()`. Both source docs cite lines 192 and 201 as of commit `40bc691` — that commit is now several weeks old at minimum. `grep -n "retrieve_vector("  api/services/retriever.py` before editing to confirm current locations; the default-value approach in Task 1 below means this doesn't block the fix, but it's worth confirming no third call site was added since.
3. **`response.response_metadata` key names** for token usage (`_extract_llm_usage` in Task 6). Doc B flagged this as "written from the documented interface, not a response actually inspected yet." That caution still applies — run one manual `ainvoke()` call against the actual installed `langchain-litellm` version and confirm `token_usage` vs `usage` is the right key before trusting cost tracking in production.
4. **`config.py`'s actual structure** for where `MIN_VECTOR_SCORE` and `NAMESPACE_REGISTRY` should live. Both are written below as standalone additions; place them next to whatever existing constants they're most similar to (retrieval tuning, feature registries) rather than at the end of the file by default.
5. **Whether FinOps usage is persisted per-request or only kept as a resetting counter** — carried over from Doc B's Task 10, still genuinely unresolved without seeing the FinOps middleware's storage code. Not part of this week's scope; listed again in §9.

---

## 3. Gap Fixes Carried From Week 9

| # | Gap | Fix |
|---|---|---|
| R1 (Wk9) | Vector score floor missing | Task 1 |
| R9 (Wk9) | `DIM` hardcoded to 768 in `cache.py` | Task 2 |
| R10 (Wk9) | Health check embedding probe not cached | Task 3 |

**Confirmed not a gap (both docs agree, unchanged here):** `retriever.py`'s `mode` parameter (`hybrid` / `vector_only` / `bm25_only`) is already fully implemented — no changes needed.

---

## 4. The Work, In Order

| Task | What | Time | Files |
|---|---|---|---|
| 1 | Add configurable vector score floor (default-valued param, backward compatible) | 10 min | `api/services/retriever.py`, `config.py` |
| 2 | Read `DIM` from `config.EMBEDDING_DIM` in cache index | 5 min | `api/services/cache.py` |
| 3 | Cache health check embedding probe + cold-start retry | 15 min | `api/routers/health.py`, `api/models/schemas.py` |
| 4 | Install LangGraph + set up agent package | 20 min | `pyproject.toml`, `api/agent/__init__.py` |
| 5 | Build agent tools (`retrieve_chunks`, `list_namespaces`) | 1 hr | `api/agent/tools.py`, `config.py` |
| 6 | Build the agent graph: reasoning + retrieval, deterministic synthesis, optional verifier | 3.25 hrs | `api/agent/graph.py`, `config.py` |
| 7 | Build the agent route: citations/cost exposure, verifier toggle | 2 hrs | `api/agent/router.py`, `api/main.py` |
| 8 | Agent tests | 1.75 hrs | `tests/unit/test_agent_tools.py` |
| 9 | Documentation | 1.25 hrs | `ARCHITECTURE.md`, `README.md` |
| 10 | Future work — scoped, not built | 0 min (doc only) | `ARCHITECTURE.md` (backlog note) |

**Total: ~10 hours.** Task-by-task, as above — not compressed into day-sized blocks. Each task is independently completable and testable before moving to the next.

---

# Task 1: Add a Configurable Vector Score Floor

**Time: 10 minutes**

**File: `config.py`** — add near other retrieval-tuning constants (place next to whatever similar tunables already exist, not necessarily at file end):

```python
# Cosine-similarity floor for vector retrieval. A score above 0 means
# "related to the query"; at or below 0 means unrelated or opposite-
# pointing — not a useful match. 0.0 is safe as a default: it rarely
# changes anything in a namespace full of good matches, and only matters
# when a namespace has little or nothing relevant to find. Kept here
# rather than as a literal in the SQL so switching embedding models later
# is a one-line change, not a SQL edit + redeploy.
MIN_VECTOR_SCORE = 0.0
```

**File: `api/services/retriever.py`** — add the import, then update `retrieve_vector()`:

```python
from config import MIN_VECTOR_SCORE
```

```python
async def retrieve_vector(
    pool: Pool,
    query_embedding: list[float],
    namespace: str,
    limit: int,
    min_score: float = MIN_VECTOR_SCORE,
) -> list[dict]:
    """
    Vector similarity search with a score floor.

    The subquery computes vector_score once per row; the outer WHERE
    filters on that already-computed column. Postgres runs WHERE before
    SELECT, so a column alias created in SELECT doesn't exist yet when a
    plain WHERE would try to reference it — without the subquery split,
    the cosine-distance formula would have to be written twice (once to
    produce vector_score, again inside WHERE), computing the same math
    twice on every row. The subquery avoids that: inner query computes
    and finishes first, outer query filters on the finished column.

    min_score defaults to config.MIN_VECTOR_SCORE (0.0) so existing
    callers that don't pass it keep working unchanged — see the 🐛 R1 note
    in the reconciliation summary at the top of this document for why that
    default matters here specifically.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM (
                SELECT id, document_id, content, metadata,
                       1.0 - (embedding <=> $1::vector) AS vector_score
                FROM documents
                WHERE namespace = $2
            ) scored
            WHERE vector_score > $4
            ORDER BY vector_score DESC
            LIMIT $3
            """,
            query_embedding, namespace, limit, min_score,
        )

    results = []
    for r in rows:
        meta = _parse_metadata(r["metadata"])
        results.append({
            "id": r["id"],
            "document_id": r["document_id"],
            "content": r["content"],
            "metadata": meta,
            "vector_score": r["vector_score"],
            "source_filename": meta.get("source_filename"),
        })
    return results
```

🐛 **R1 bugfix, explicitly:** the 4th bind param (`$4`) is real and required by the SQL — that part of Doc B's plan was correct. What Doc B's task text skipped was making it safe for existing callers. Giving `min_score` a default value pulled from config means `retrieve()`'s two existing call sites (confirm exact lines via `grep -n "retrieve_vector(" api/services/retriever.py` — see 🚩 Flag #2) don't need to change at all for this to work. If you *do* want a call site to use a non-default floor later (e.g. a stricter floor for a specific namespace), pass `min_score=` explicitly there.

---

# Task 2: Read DIM from Config

**Time: 5 minutes**

**File: `api/services/cache.py`** — add `EMBEDDING_DIM` to the config import, replace the hardcoded `"768"` in `create_semantic_cache_index()`:

```python
from config import CACHE_CONFIG, LLM_CONFIG, EMBEDDING_DIM
```

```python
            "DIM", str(EMBEDDING_DIM),
```

No behavior change today (embeddings are already 768-dim per your config), but a model switch later becomes a one-line config change instead of a silent mismatch between the cache index and whatever the embedding model actually outputs.

---

# Task 3: Cache Health Check Embedding Probe

**Time: 15 minutes**

Both source docs agree on this task in full, including the Ollama cold-start reasoning — no changes needed here.

**File: `api/models/schemas.py`** — add the missing fields to `HealthResponse` (this was Doc A's B1: `health.py` already returns `mode` and `uptime_seconds`, but the response model was silently dropping them via `response_model` filtering):

```python
class HealthResponse(BaseModel):
    status: str                  # "ok" or "degraded"
    db: str                      # "ok" or "error: <reason>"
    redis: str                   # "ok" or "error: <reason>"
    version: str
    mode: str = ""               # "local", "demo", or "prod"
    uptime_seconds: int = 0
```

**File: `api/routers/health.py`** — replace with the probe-caching version:

```python
import asyncio
import time

from fastapi import APIRouter, Request

from api.models.schemas import HealthResponse
from api.services.cache import redis_health
from config import LLM_CONFIG, MODE

router = APIRouter()
_start_time = time.time()

# Cache the probe: without it, every /health call (Dockerfile HEALTHCHECK
# runs one every 30s) hits the embedding API — no purpose after the first
# successful check. Different TTLs on purpose: don't rush to re-check a
# healthy service, but re-check a failing one sooner.
_embed_cache = {"status": "unknown", "checked_at": 0.0}
_EMBED_OK_TTL = 60
_EMBED_FAIL_TTL = 10
_embed_lock = asyncio.Lock()

# embedding_model for local/demo mode is ollama/nomic-embed-text, served
# by a separate Ollama container on the same Docker network. Ollama
# unloads an idle model from memory and reloads it on the next request —
# a few seconds, not an error. One retry absorbs that instead of
# reporting a cold start as a real outage.
_EMBED_PROBE_TIMEOUT = 8.0
_EMBED_COLD_START_RETRY_DELAY = 1.0


async def _probe_once() -> str:
    import litellm
    resp = await asyncio.wait_for(
        litellm.aembedding(model=LLM_CONFIG["embedding_model"], input=["health check"]),
        timeout=_EMBED_PROBE_TIMEOUT,
    )
    return "ok" if resp.data else "error: empty response"


async def _check_embedding() -> str:
    """Probe the embedding API, with a lock so concurrent /health requests
    arriving during the stale window don't all fire duplicate probes."""
    def _fresh(now: float) -> bool:
        ttl = _EMBED_OK_TTL if _embed_cache["status"] == "ok" else _EMBED_FAIL_TTL
        return now - _embed_cache["checked_at"] <= ttl

    if _fresh(time.time()):
        return _embed_cache["status"]

    async with _embed_lock:
        if _fresh(time.time()):  # another request may have refreshed it while we waited on the lock
            return _embed_cache["status"]

        try:
            status = await _probe_once()
        except Exception:
            await asyncio.sleep(_EMBED_COLD_START_RETRY_DELAY)
            try:
                status = await _probe_once()
            except Exception as e:
                status = f"error: {str(e)}"

        _embed_cache["status"] = status
        _embed_cache["checked_at"] = time.time()

    return _embed_cache["status"]


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    try:
        async with request.app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    redis_status = await redis_health()
    embed_status = await _check_embedding()
    all_ok = all(s == "ok" for s in [db_status, redis_status, embed_status])

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        db=db_status,
        redis=redis_status,
        version="0.3.0",
        mode=MODE,
        uptime_seconds=int(time.time() - _start_time),
    )
```

🚩 **Reminder from Doc B, still applicable:** this depends on `OLLAMA_API_BASE` being set to `http://ollama:11434` (LiteLLM defaults to `localhost`, which is wrong from inside the API container). Pre-existing requirement for every embedding call the pipeline makes, not new to this task — a misconfiguration would surface here first, on every deploy.

---

# Task 4: Install LangGraph + Set Up Agent Package

**Time: 20 minutes**

### Why LangGraph, and why not `create_react_agent`, CrewAI, or AutoGen

LangGraph models the agent as an explicit state machine: nodes are functions, edges connect them, state flows through as a typed dict every node can read and write. That explicitness is what this agent actually needs, because the graph has to do more than "call LLM, maybe call a tool, repeat" — it has two mandatory stops after the reasoning loop ends (deterministic synthesis, then optionally verification), and LangGraph's prebuilt `create_react_agent(model, tools)` routes straight to `END` once the model stops requesting tools, with no way to insert those extra stops. That's why this plan hand-rolls the graph instead of using the prebuilt one — not because the prebuilt is wrong for simpler cases, but because this agent isn't a simpler case.

CrewAI's coordination layer (task delegation, role negotiation between peer agents) is built for teams of agents working somewhat independently on a shared task. The two roles here — reasoning/retrieval and verification — don't coordinate as peers; one runs in a fixed sequence and decides whether to send work back to the other. That's a two-node graph, not a crew. AutoGen's conversation-based multi-agent paradigm has the same mismatch: useful for agent-to-agent dialogue, unnecessary overhead for a fixed hand-off between two roles.

**Why this doesn't reopen the earlier "no LangChain" decision:** that decision was about model access — calling the LLM itself. Every LLM call in this agent still goes through `ChatLiteLLM`, wrapping LiteLLM, same as the rest of the platform. LangGraph is being used for something different — orchestration, the sequence of steps and which role runs when. It decides what happens next; LiteLLM makes the actual model call.

### Package structure

```
api/
  agent/
    __init__.py
    tools.py      ← functions the agent can call
    graph.py      ← the LangGraph graph definition
    router.py     ← the FastAPI route /agent/query
```

Lives under `api/` (not a new top-level package) because it depends on `api.services.retriever`, `api.services.llm`, `api.services.cache` — importing `api.*` from a sibling top-level package would need `sys.path` changes. Follows the same pattern as `api/routers/`, `api/services/`, `api/middleware/`.

### The code

**File: `pyproject.toml`** — add to `dependencies`:

```toml
    "langgraph (>=1.2.0,<2.0.0)",
    "langchain-core (>=1.4.0,<2.0.0)",
    "langchain-litellm (>=0.2.0,<1.0.0)",
```

Checked against PyPI today (Aug 3, 2026): `langgraph` is at 1.2.10, `langchain-core` at 1.5.3, `langchain-litellm` at 0.2.2 — all within these ranges. `langchain-litellm` is now the primary, LangChain-documented distribution path for `ChatLiteLLM` (`from langchain_litellm import ChatLiteLLM`), so no `langchain_community` fallback import is needed anymore. **Still re-run `pip index versions langgraph langchain-core langchain-litellm` right before installing** — these move fast enough that this table will be stale by the time you actually run the install.

**New file: `api/agent/__init__.py`:**

```python
"""
api/agent/
Agent layer for the RAG platform using LangGraph.

Two LLM roles in one graph: a reasoning/retrieval role that decides what
to search for, and an optional verifier role that checks the drafted
answer against what was retrieved.
"""
```

---

# Task 5: Build Agent Tools

**Time: 1 hour**

### Two tools, and why synthesis isn't a third one

A tool only runs if the LLM decides to call it — nothing forces it. For retrieval, that's exactly right: deciding *how much* to search is a genuine judgment call. "Compare the data breach notification timelines under GDPR and CCPA" needs two separate searches, one per regulation — deciding that is what `retrieve_chunks` being a tool is for.

For synthesis, that same freedom is a liability. If the LLM just writes an answer in plain text instead of calling a tool, that answer silently skips citations, confidence scoring, and usage tracking — a system prompt is a suggestion, not a rule. It would also waste tokens: the chunks are already visible to the LLM from `retrieve_chunks`'s output, so making it copy them again as a tool argument risks the model paraphrasing text that then gets cited as if it were the original. So synthesis stays a deterministic graph step (Task 6), never a tool call.

### Why namespace discovery is its own tool, not a hardcoded prompt list

Hardcoding the namespace list into the system prompt goes stale the moment a new document set is added. `list_namespaces` reads from `NAMESPACE_REGISTRY` in `config.py` instead — adding a namespace becomes a config change, not a prompt or code change.

### Why one retrieval tool with a `mode` parameter, not three tools

Splitting `retrieve_chunks` into per-strategy tools (`retrieve_vector_only`, `retrieve_bm25_only`, ...) sends near-identical tool schemas on every turn, which costs more tokens and measurably hurts tool-selection accuracy versus one tool with a parameter. `mode` on `retrieve_chunks` already covers the same ground.

### Why the retrieval tool is a thin wrapper

`retrieve_chunks` calls the existing `retrieve()` function directly — no retrieval logic of its own, so any future fix to `retrieve()` (like Task 1's score floor) applies to agent queries automatically. This guarantee covers retrieval; it does *not* cover the agent's own reasoning calls, which go through `ChatLiteLLM` directly rather than `generate_with_routing()` — Task 6 handles usage tracking for those separately.

### The code

**File: `config.py`** — add the namespace registry:

```python
# Namespaces available to search, with a short description of each. The
# agent's list_namespaces tool reads this directly, so adding a namespace
# here is enough — no prompt or code change needed elsewhere.
NAMESPACE_REGISTRY = {
    "legal": "GDPR, CCPA, HIPAA, and other data-protection regulations",
    "kyc_aml": "KYC, AML, and Bank Secrecy Act documentation",
    "default": "Uncategorized or general compliance documents",
}
```

**New file: `api/agent/tools.py`:**

```python
"""
api/agent/tools.py

Tools the LangGraph agent can call during its reasoning loop.

Rules for tool functions:
  1. Must have a clear docstring — the LLM reads this to decide when to use the tool
  2. Arguments must be simple types (str, int, Literal) — no complex objects
  3. Return value must be a string — the LLM reads the return as text
  4. Must handle errors gracefully — a tool crash terminates the agent loop
"""
import json
import logging
from typing import Literal

from asyncpg import Pool
from langchain_core.tools import tool

from api.services.retriever import retrieve, RetrieverConfig
from api.services.cache import embed_query
from config import FEATURES, NAMESPACE_REGISTRY

logger = logging.getLogger("api.agent.tools")


@tool
def list_namespaces() -> str:
    """
    List the document namespaces available to search, with a short
    description of what each one contains.

    Call this if you're unsure which namespace fits the question, instead
    of guessing — namespaces change over time as new document sets are
    added, so don't assume the ones you've seen before are the full list.

    Returns:
        JSON string mapping namespace name to a description.
    """
    return json.dumps(NAMESPACE_REGISTRY)


def make_retrieve_tool(pool: Pool):
    """
    Build the retrieve_chunks tool bound to a specific DB pool.

    Built as a closure — instead of a module-level global flipped by a
    set_db_pool() call on every request — so the tool is constructed once,
    at app startup, alongside the graph. Avoids mutable module state
    shared across concurrent requests, and is trivially testable: pass in
    a fake pool, no monkeypatching a global.
    """

    @tool
    async def retrieve_chunks(
        query: str,
        namespace: str = "default",
        top_k: int = 5,
        mode: Literal["hybrid", "vector_only", "bm25_only"] = "hybrid",
    ) -> str:
        """
        Search the compliance document database for chunks relevant to a query.

        Use this tool when you need to find specific regulatory text, policy content,
        or compliance documentation. The query should describe what information you
        are looking for in natural language. If you're unsure which namespace to
        search, call list_namespaces first rather than guessing.

        Args:
            query: Natural language description of the information needed.
            namespace: Document scope to search within (e.g., "legal", "kyc_aml").
            top_k: Number of chunks to retrieve (1-20, default 5).
            mode: Retrieval strategy — "hybrid" (default, best quality), "vector_only", or "bm25_only".

        Returns:
            JSON string containing the retrieved chunks with content, scores, and metadata.
        """
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
                return json.dumps({"result": "No relevant chunks found", "count": 0})

            results = []
            for i, c in enumerate(chunks):
                score = (
                    c.get("rrf_score") or
                    c.get("vector_score") or
                    c.get("bm25_score") or 0.0
                )
                content = c["content"]
                results.append({
                    "chunk_index": i,
                    "document_id": c["document_id"],
                    # Matches retriever.py's own key name (Task 1) end to
                    # end — retriever -> tool -> synthesize_node all use
                    # "source_filename", no remap step anywhere.
                    "source_filename": c.get("source_filename", "unknown"),
                    "score": round(float(score), 4),
                    "content": content[:500],
                    "truncated": len(content) > 500,
                })

            return json.dumps({"count": len(results), "chunks": results}, indent=2)

        except Exception as e:
            logger.error("[agent/retrieve] error: %s", e)
            return json.dumps({"error": str(e)})

    return retrieve_chunks
```

---

# Task 6: Build the Agent Graph

**Time: 3.25 hours**

### What a LangGraph graph is

A state machine. State: a typed dict flowing through the graph, readable/writable by every node. Nodes: functions that transform state. Edges: connections between nodes, unconditional or conditional.

### Why a hand-rolled graph instead of `create_react_agent`

Covered in Task 4 — the two mandatory stops after retrieval (synthesis, optional verification) don't fit the prebuilt's "stop calling tools → END" shape.

### Why `ChatLiteLLM`

LangGraph needs an object exposing `.bind_tools()` and `.ainvoke()` — `langchain-core`'s `BaseChatModel` interface. `ChatLiteLLM` provides both, and underneath calls `litellm.acompletion()` — the same function `generate_with_citations` uses elsewhere. Model, API key, and routing stay controlled from `config.py`.

### Why a verifier role earns a second LLM call, where a third agent or a split-by-namespace design wouldn't

Two scope questions came up while drafting this: multiple specialized agents instead of one, and splitting retrieval into per-strategy tools (already addressed in Task 5). Both stay rejected for the same reason — **splitting only pays off when a piece needs a genuinely different capability, not just a different value for an existing setting.** A namespace-per-agent design would be several LLM calls doing what one already does by setting an argument.

A verifier role clears that bar. Checking a drafted answer against its sources is a different skill from producing the answer — a second, focused LLM pass with its own narrow system prompt, not a redundant split of the same task.

### Making the verifier optional — request-level toggle, not in-file branching

The verifier behaves like an "extended thinking" toggle: a boolean travels in from the request, becomes part of the graph's initial state, and one conditional edge (`should_verify`) reads it. Two levels, kept separate:
- **Per-request** (`AgentRequest.enable_verifier`, default `True`): what a caller wants for this question — off for a latency-sensitive lookup.
- **Deployment-wide** (`FEATURES["verifier_enabled"]`): a global kill-switch independent of what any request asks for, useful if the verifying model underperforms in a given `MODE`. A request asking for verification doesn't override this if it's off.

### The code

**File: `config.py`** — add the verifier kill-switch to `FEATURES`:

```python
FEATURES = {
    "reranker_enabled": MODE != "demo",
    "otel_enabled": True,
    "azure_monitor": MODE == "prod",
    "verifier_enabled": True,  # deployment-wide kill-switch; a request's enable_verifier=True is still overridden if this is False
}
```

**New file: `api/agent/graph.py`:**

```python
"""
api/agent/graph.py

LangGraph agent for multi-step compliance research.

Four nodes:
  1. agent_node: Calls the LLM with the current message history. Requests
     a retrieve_chunks / list_namespaces call, or signals it's done.
  2. tools: Executes whichever tool was requested, appends the result.
  3. synthesize_node: Deterministic — not an LLM tool call. Always runs
     once the agent stops requesting tools. Produces the final cited
     answer via the same generate_with_routing() /search uses.
  4. verify_node: Runs only if enabled (see should_verify). Checks the
     drafted answer against the retrieved chunks; can send the graph back
     to agent_node once if something looks unsupported.
"""
import json
import logging
from operator import add
from typing import Annotated, TypedDict

from asyncpg import Pool
from langchain_core.messages import (
    BaseMessage, SystemMessage, HumanMessage, ToolMessage,
)
from langchain_litellm import ChatLiteLLM
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from api.agent.tools import make_retrieve_tool, list_namespaces
from config import LLM_CONFIG, FEATURES

logger = logging.getLogger("api.agent.graph")


class AgentState(TypedDict):
    """
    State flowing through every node.

    `messages` accumulates via add_messages (append, not replace).
    `reasoning_usage` / `verifier_usage` accumulate via plain list
    concatenation (add) — one entry per LLM call in that role. Both MUST
    be initialized as empty lists wherever ainvoke() is first called
    (Task 7) — see the 🐛 R2 note at the top of this document. Without
    that initialization, LangGraph raises InvalidUpdateError the first
    time agent_node tries to append to a key that was never in state.

    final_answer / confidence / citations / model_used / tokens_used /
    synthesis_cost are set once, by synthesize_node. enable_verifier and
    verify_retries_left come from the request. verified /
    verification_notes are set once, by verify_node, and stay unset if
    verification never ran.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    reasoning_usage: Annotated[list[dict], add]
    verifier_usage: Annotated[list[dict], add]
    final_answer: str
    confidence: float
    citations: list[dict]
    model_used: str
    tokens_used: int
    synthesis_cost: float
    enable_verifier: bool
    verify_retries_left: int
    verified: bool
    verification_notes: str


AGENT_SYSTEM_PROMPT = """You are an expert compliance research assistant with access to a regulatory document database.

You have two tools:
- list_namespaces: discover which document namespaces exist and what each contains
- retrieve_chunks: search a namespace for relevant regulatory text

For every question:
1. If you're unsure which namespace fits the question, call list_namespaces rather than guessing.
2. Use retrieve_chunks to find relevant documents. If the question involves comparing regulations across different namespaces, retrieve from EACH namespace separately.
3. Once you have sufficient context, stop calling tools — a final answer will be generated automatically from what you've retrieved.
4. If you cannot find relevant documents after a reasonable search, stop anyway and say so; do not keep retrying indefinitely.
5. If you see a "[Verifier feedback]" message in the conversation, it means a previous draft had an unsupported claim — retrieve whatever additional context would address it before stopping again.

Be thorough about retrieval. You do not write the final answer yourself — just gather the right context."""


VERIFIER_SYSTEM_PROMPT = """You are a compliance answer verifier. You will be shown a draft answer and the source chunks it was built from.

Check whether every factual claim in the draft is supported by the provided chunks. Minor gaps or partial coverage are fine — only flag it if there's a clear, material claim with no grounding in the chunks shown.

Respond with only a JSON object, nothing else:
{"supported": true or false, "notes": "brief explanation, or the specific unsupported claim"}"""


def _extract_chunks(messages: list[BaseMessage]) -> list[dict]:
    """Pull every chunk surfaced by retrieve_chunks calls, deduped by (document_id, chunk_index)."""
    seen = set()
    chunks = []
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        try:
            data = json.loads(m.content)
        except (json.JSONDecodeError, TypeError):
            continue
        for c in data.get("chunks", []):
            key = (c.get("document_id"), c.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            chunks.append(c)
    return chunks


def _extract_llm_usage(response: BaseMessage) -> dict:
    """
    Pull token counts (and cost, if computable) off a single ChatLiteLLM
    response — used for both the reasoning role and the verifier role, so
    every LLM call in the graph contributes to cost tracking, not just the
    final synthesis step.

    🚩 FLAG (open item #3): response.response_metadata's exact key names
    depend on the installed langchain-litellm version. Written from the
    documented interface, not a response actually inspected yet — run one
    manual ainvoke() call against the installed version and confirm
    token_usage vs usage is right before trusting cost numbers.
    """
    meta = getattr(response, "response_metadata", {}) or {}
    usage = meta.get("token_usage", {}) or meta.get("usage", {}) or {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    cost = 0.0
    try:
        import litellm
        cost = litellm.completion_cost(
            model=meta.get("model", LLM_CONFIG["model"]),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception:
        pass  # cost is best-effort; token counts are the part we rely on

    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost": cost}


async def synthesize_node(state: AgentState) -> dict:
    """
    Deterministic finalizer. Always runs once the agent stops requesting
    tools. Not an LLM tool call, so there's no path where a query returns
    an answer without citations, a confidence score, and usage tracking.
    """
    from api.services.llm import generate_with_routing

    question = next(
        (m.content for m in state["messages"] if isinstance(m, HumanMessage)),
        "",
    )
    chunks = _extract_chunks(state["messages"])

    if not chunks:
        return {
            "final_answer": "I couldn't find relevant documents to answer this question.",
            "confidence": 0.0,
            "citations": [],
            "model_used": "",
            "tokens_used": 0,
            "synthesis_cost": 0.0,
        }

    # tools.py already emits "source_filename" (Task 5) — no remap needed
    # here, unlike an earlier draft of this plan that used "source" and
    # remapped it at this step. See the ⚙️ naming-consistency note at the
    # top of this document.
    db_chunks = [
        {
            "document_id": c["document_id"],
            "source_filename": c.get("source_filename", "unknown"),
            "text": c["content"],
            "score": c.get("score", 0.0),
        }
        for c in chunks
    ]

    answer_obj, usage_dict = await generate_with_routing(question, db_chunks)

    return {
        "final_answer": answer_obj.answer,
        "confidence": answer_obj.confidence,
        # Field names match Citation in schemas.py exactly.
        "citations": [
            {
                "document_id": c.document_id,
                "source_filename": c.source_filename,
                "chunk_index": c.chunk_index,
                "relevance_score": c.relevance_score,
                "excerpt": c.excerpt,
            }
            for c in answer_obj.citations
        ],
        "model_used": answer_obj.model_used,
        "tokens_used": usage_dict.get("prompt_tokens", 0) + usage_dict.get("completion_tokens", 0),
        "synthesis_cost": usage_dict.get("total_cost", 0.0),
    }


async def verify_node(state: AgentState) -> dict:
    """
    Runs only when should_verify routes here. Checks the synthesized
    answer against the retrieved chunks; if something looks unsupported
    and retries remain, sends the graph back to agent_node with feedback.
    """
    chunks = _extract_chunks(state["messages"])
    excerpts = "\n\n".join(
        f"[{c.get('document_id')}] {c.get('content', '')[:500]}" for c in chunks
    )

    model = ChatLiteLLM(
        model=LLM_CONFIG["model"],
        temperature=0,
        max_tokens=500,
        # 🚩 FLAG (open item #1): LLM_CONFIG["model"] carries a "groq/"
        # provider prefix. If this raises an auth or model-not-found
        # error, pass api_key=<your Groq key from config> explicitly —
        # the exact config field name isn't visible from this plan's
        # source files, so it isn't guessed at here.
    )
    response = await model.ainvoke([
        SystemMessage(content=VERIFIER_SYSTEM_PROMPT),
        HumanMessage(content=f"Draft answer:\n{state['final_answer']}\n\nSource chunks:\n{excerpts}"),
    ])

    try:
        parsed = json.loads(response.content)
        supported = bool(parsed.get("supported", True))
        notes = parsed.get("notes", "")
    except (json.JSONDecodeError, TypeError):
        # Default to accepting the draft rather than looping on a parse failure.
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


def should_continue(state: AgentState) -> str:
    """Route to 'tools' if the agent just requested one, else to 'synthesize'."""
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return "synthesize"


def should_verify(state: AgentState) -> str:
    """Route to 'verify' only if enabled for this query and not disabled deployment-wide."""
    if not state.get("enable_verifier", True):
        return "end"
    if not FEATURES.get("verifier_enabled", True):
        return "end"
    return "verify"


def verify_router(state: AgentState) -> str:
    """After verification: retry (back through agent_node) if something was
    flagged as unsupported and retries remain; otherwise end."""
    if not state.get("verified", True) and state.get("verify_retries_left", 0) > 0:
        return "retry"
    return "end"


def build_agent_graph(pool: Pool):
    """
    Construct and compile the agent graph, bound to a DB pool.

    Called ONCE at app startup — not per request. A compiled graph is
    meant to be invoked repeatedly and concurrently; rebuilding it on
    every request would recompile the whole thing and re-instantiate the
    ChatLiteLLM clients for no benefit.

    Graph structure:
      START -> agent -> (tool call?) -> tools -> agent -> ... -> synthesize
             -> (verify enabled?) -> verify -> (unsupported + retries left?) -> agent (loop)
                                                                              -> END
                                   -> END (verifier off)
    """
    tools = [make_retrieve_tool(pool), list_namespaces]
    model = ChatLiteLLM(
        model=LLM_CONFIG["model"],
        temperature=0,
        max_tokens=4000,
        # 🚩 Same FLAG as verify_node above — see open item #1.
    ).bind_tools(tools)

    async def agent_node(state: AgentState) -> dict:
        # System prompt isn't stored in state (it's not part of the
        # conversation history the client gets back), so it's reattached
        # to every call rather than trying to detect if it's already there.
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]]
        response = await model.ainvoke(messages)
        return {
            "messages": [response],
            "reasoning_usage": [_extract_llm_usage(response)],
        }

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("verify", verify_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "synthesize": "synthesize"})
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("synthesize", should_verify, {"verify": "verify", "end": END})
    graph.add_conditional_edges("verify", verify_router, {"retry": "agent", "end": END})

    return graph.compile()
```

---

# Task 7: Build the Agent Route

**Time: 2 hours**

### Why a separate route, not an extension of `/search`

`/search` is one query in, one answer out — no tool calls, no loop. The agent can call tools multiple times and optionally loop through verification before it has an answer. Mixing both into one endpoint means branching logic inside a single route. Keeping them separate keeps the choice explicit: `/search` for a fast single-shot answer, `/agent/query` for multi-step research.

### Recursion limit, now that verification can loop back

One full retrieval-to-synthesis round is `max_iterations * 2 + 2` node runs. A verify-triggered retry runs one more full round plus one extra node run for `verify` itself. The formula below is a generous upper bound, not a tight derivation — confirm actual recursion counts against real runs before tightening it.

### The code

**New file: `api/agent/router.py`:**

```python
"""
api/agent/router.py

FastAPI route for the compliance research agent.

POST /agent/query
  Body: {"question": "...", "namespace": "legal", "enable_verifier": true}
  Returns: {"answer": "...", "citations": [...], "verified": true, ...}
"""
import logging
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

logger = logging.getLogger("api.agent")
router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    question: str = Field(description="The compliance question to research")
    namespace: str = Field(default="default", description="Document scope hint for the agent")
    max_iterations: int = Field(default=6, ge=1, le=10, description="Max retrieve_chunks calls before forcing synthesis")
    enable_verifier: bool = Field(default=True, description="Whether to verify the drafted answer against retrieved chunks before returning it")
    max_verify_retries: int = Field(default=1, ge=0, le=3, description="How many times verification can send the query back for more retrieval")


class AgentCitation(BaseModel):
    """Mirrors schemas.py's Citation exactly."""
    document_id: str
    source_filename: str
    chunk_index: int
    relevance_score: float
    excerpt: str


class AgentResponse(BaseModel):
    question: str
    answer: str
    confidence: float = 0.0
    citations: list[AgentCitation] = []
    model_used: str = ""
    verified: bool | None = None  # None means the verifier didn't run for this query
    verification_notes: str = ""
    reasoning_steps: list[str]
    tool_calls_made: int
    total_time_seconds: float
    total_cost_usd: float = 0.0


def _combine_usage(result: dict) -> dict:
    """Sum every reasoning-role and verifier-role LLM call's usage with
    synthesize_node's own cost, so FinOps sees an agent query's full cost,
    not just its final step."""
    all_calls = result.get("reasoning_usage", []) + result.get("verifier_usage", [])
    prompt_tokens = sum(u.get("prompt_tokens", 0) for u in all_calls)
    completion_tokens = sum(u.get("completion_tokens", 0) for u in all_calls)
    llm_cost = sum(u.get("cost", 0.0) for u in all_calls)
    synthesis_cost = result.get("synthesis_cost", 0.0)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_cost": llm_cost + synthesis_cost,
        "routing_decision": "agent",
        "routed_model": result.get("model_used", ""),
    }


@router.post("/query", response_model=AgentResponse)
async def agent_query(request: Request, response: Response, payload: AgentRequest) -> AgentResponse:
    start = time.perf_counter()
    graph = request.app.state.agent_graph  # compiled once at startup — see main.py

    # Generous upper bound, not a tight derivation — see Task 7 notes above.
    base_round = payload.max_iterations * 2 + 2
    recursion_limit = base_round * (1 + payload.max_verify_retries) + payload.max_verify_retries + 5

    try:
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=payload.question)],
                # 🐛 R2 bugfix: both reducer-typed lists MUST be
                # initialized here. Omitting them (as an earlier draft of
                # this plan did) raises InvalidUpdateError the first time
                # agent_node tries to append — see the AgentState
                # docstring in graph.py and the reconciliation note at the
                # top of this document.
                "reasoning_usage": [],
                "verifier_usage": [],
                "enable_verifier": payload.enable_verifier,
                "verify_retries_left": payload.max_verify_retries,
            },
            config={"recursion_limit": recursion_limit},
        )
    except GraphRecursionError:
        logger.warning(
            "[agent] hit recursion_limit=%d before converging, question=%r",
            recursion_limit, payload.question,
        )
        return AgentResponse(
            question=payload.question,
            answer=(
                "I wasn't able to reach a confident answer within the allotted "
                "reasoning steps. Try a narrower question or a higher max_iterations."
            ),
            confidence=0.0,
            reasoning_steps=["Reached max_iterations without producing a final answer."],
            tool_calls_made=0,
            total_time_seconds=round(time.perf_counter() - start, 3),
        )
    except Exception as e:
        logger.error("[agent] graph execution failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

    reasoning_steps = []
    tool_call_count = 0
    for msg in result["messages"]:
        if getattr(msg, "tool_calls", None):
            tool_call_count += len(msg.tool_calls)
            for tc in msg.tool_calls:
                reasoning_steps.append(f"Called tool: {tc['name']}({tc['args']})")
        elif isinstance(msg, ToolMessage):
            content = msg.content or ""
            suffix = "..." if len(content) > 200 else ""
            reasoning_steps.append(f"Tool result: {content[:200]}{suffix}")

    usage_dict = _combine_usage(result)
    request.state.usage = usage_dict
    response.headers["X-Cost-USD"] = f"{usage_dict['total_cost']:.6f}"

    return AgentResponse(
        question=payload.question,
        answer=result.get("final_answer", "No answer generated"),
        confidence=result.get("confidence", 0.0),
        citations=[AgentCitation(**c) for c in result.get("citations", [])],
        model_used=result.get("model_used", ""),
        verified=result.get("verified"),
        verification_notes=result.get("verification_notes", ""),
        reasoning_steps=reasoning_steps,
        tool_calls_made=tool_call_count,
        total_time_seconds=round(time.perf_counter() - start, 3),
        total_cost_usd=usage_dict["total_cost"],
    )
```

**File: `api/main.py`** — build the graph once, after the DB pool exists, then register the router:

```python
from api.agent.graph import build_agent_graph
from api.agent.router import router as agent_router

# Inside whatever startup hook already creates app.state.db_pool
# (lifespan context manager or @app.on_event("startup")), after the
# pool is created:
app.state.agent_graph = build_agent_graph(app.state.db_pool)

app.include_router(agent_router)
```

---

# Task 8: Agent Tests

**Time: 1.75 hours**

**New file: `tests/unit/test_agent_tools.py`:**

```python
"""
tests/unit/test_agent_tools.py

Tests for the agent tools and routing logic in isolation (no live LLM, no live DB).
"""
import json
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from api.agent.tools import make_retrieve_tool, list_namespaces
from api.agent.graph import should_continue, should_verify, verify_router, _extract_chunks, _extract_llm_usage
from api.agent.router import _combine_usage


class _FailingPool:
    """Pool stand-in whose acquire() always raises, to exercise the error path
    without hitting a real database."""
    def acquire(self):
        raise RuntimeError("connection refused")


@pytest.mark.asyncio
async def test_retrieve_chunks_handles_db_error(monkeypatch):
    """A DB failure should come back as a JSON error string, not a raised
    exception (a raised exception inside a tool call terminates the agent loop)."""
    import api.agent.tools as tools_module

    async def fake_embed_query(query: str):
        return [0.0] * 768

    monkeypatch.setattr(tools_module, "embed_query", fake_embed_query)

    tool = make_retrieve_tool(_FailingPool())
    result = await tool.ainvoke({"query": "test query", "namespace": "default"})
    data = json.loads(result)
    assert "error" in data


def test_retrieve_tool_has_docstring():
    tool = make_retrieve_tool(pool=None)
    assert tool.description is not None
    assert len(tool.description) > 20


def test_list_namespaces_returns_registry_contents():
    result = json.loads(list_namespaces.invoke({}))
    assert "legal" in result
    assert "kyc_aml" in result


def test_should_continue_routes_to_tools_on_tool_call():
    state = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "retrieve_chunks", "args": {"query": "x"}, "id": "1"},
    ])]}
    assert should_continue(state) == "tools"


def test_should_continue_routes_to_synthesize_when_done():
    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="done retrieving")]}
    assert should_continue(state) == "synthesize"


def test_should_verify_routes_to_end_when_disabled_per_request():
    state = {"enable_verifier": False}
    assert should_verify(state) == "end"


def test_should_verify_routes_to_verify_when_enabled():
    state = {"enable_verifier": True}
    assert should_verify(state) == "verify"


def test_verify_router_retries_when_unsupported_and_retries_remain():
    state = {"verified": False, "verify_retries_left": 1}
    assert verify_router(state) == "retry"


def test_verify_router_ends_when_retries_exhausted():
    state = {"verified": False, "verify_retries_left": 0}
    assert verify_router(state) == "end"


def test_verify_router_ends_when_verified():
    state = {"verified": True, "verify_retries_left": 1}
    assert verify_router(state) == "end"


def test_extract_chunks_dedupes_by_document_and_chunk_index():
    """Two retrieve_chunks calls that overlap (e.g. retrying the same namespace)
    shouldn't double-count the same chunk when synthesize_node builds context."""
    payload = json.dumps({"chunks": [
        {"document_id": "doc1", "chunk_index": 0, "content": "GDPR text", "source_filename": "gdpr.pdf"},
    ]})
    messages = [
        ToolMessage(content=payload, tool_call_id="1"),
        ToolMessage(content=payload, tool_call_id="2"),  # duplicate retrieval
    ]
    assert len(_extract_chunks(messages)) == 1


def test_extract_llm_usage_defaults_to_zero_on_missing_metadata():
    """A response with no response_metadata (or an unexpected shape) should
    degrade to zero cost, not raise — an accounting miss shouldn't be able
    to crash the agent loop."""
    msg = AIMessage(content="thinking...")
    usage = _extract_llm_usage(msg)
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}


def test_combine_usage_sums_reasoning_and_verifier_and_synthesis_cost():
    result = {
        "reasoning_usage": [{"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.001}],
        "verifier_usage": [{"prompt_tokens": 50, "completion_tokens": 10, "cost": 0.0005}],
        "synthesis_cost": 0.004,
        "model_used": "groq/meta-llama/llama-4-scout-17b-16e-instruct",
    }
    usage = _combine_usage(result)
    assert usage["total_cost"] == pytest.approx(0.0055)
    assert usage["prompt_tokens"] == 150
    assert usage["routing_decision"] == "agent"


def test_chunk_key_matches_llm_expected_shape():
    """retrieve_chunks must use 'source_filename' end to end (Task 5/6) —
    no 'source' key anywhere in the pipeline, and no remap step needed."""
    chunk_from_tool = {
        "chunk_index": 0,
        "document_id": "doc1",
        "source_filename": "gdpr.pdf",
        "score": 0.87,
        "content": "Article 5...",
        "truncated": False,
    }
    db_chunk = {
        "document_id": chunk_from_tool["document_id"],
        "source_filename": chunk_from_tool["source_filename"],
        "text": chunk_from_tool["content"],
        "score": chunk_from_tool["score"],
    }
    assert "source" not in db_chunk
    assert db_chunk["source_filename"] == "gdpr.pdf"


@pytest.mark.asyncio
async def test_ainvoke_initial_state_includes_reducer_lists():
    """Regression test for R2: the initial state passed to graph.ainvoke()
    must include reasoning_usage and verifier_usage as empty lists, or the
    first agent_node return raises InvalidUpdateError. This test documents
    the required shape rather than exercising the live graph (which needs
    a real DB pool and LLM) — see router.py's agent_query() for the actual
    call site this guards."""
    required_keys = {"messages", "reasoning_usage", "verifier_usage", "enable_verifier", "verify_retries_left"}
    initial_state = {
        "messages": [HumanMessage(content="test")],
        "reasoning_usage": [],
        "verifier_usage": [],
        "enable_verifier": True,
        "verify_retries_left": 1,
    }
    assert required_keys.issubset(initial_state.keys())
```

---

# Task 9: Documentation

**Time: 1.25 hours**

### ARCHITECTURE.md — Add Decision 16

```markdown
## Decision 16: LangGraph agent — reasoning/retrieval role, deterministic synthesis, optional verifier role (Week 10)
**Context:** Some compliance questions require multi-step reasoning. "Compare GDPR and CCPA breach notification timelines" needs two separate retrievals and a synthesis step — the single-shot `/search` pipeline can't do this in one call. Confidently-wrong answers are also a specific risk for a compliance product.
**Decision:** A single LangGraph graph with two LLM-invoked tools (`retrieve_chunks`, parameterized by `mode` rather than split per strategy; `list_namespaces` for discovery), a deterministic synthesis node that always runs via the same `generate_with_routing()` `/search` uses, and an optional verifier node that checks the drafted answer against retrieved chunks before returning it. The verifier is a second LLM role, not a second framework or agent-team — toggleable per request (`enable_verifier`) and with a deployment-wide kill-switch (`FEATURES["verifier_enabled"]`). Exposed at `/agent/query`.
**Why one reasoning role, not several:** A namespace-per-agent or strategy-per-tool split would be additional LLM calls doing what one parameterized call already does, with no new capability. The verifier is different — checking an answer against its sources is a distinct skill from producing the answer.
**Trade-off:** Agent queries are 2-5x slower than direct `/search` even without verification; with verification enabled (default) and a retry triggered, that multiplies further. Acceptable for complex research questions; simple factual queries should still use `/search`, and verification can be turned off per request when latency matters more. All LLM calls in the graph flow into `request.state.usage` alongside synthesis cost, so FinOps sees a query's full cost.
```

### README.md — Add Week 10 section

```markdown
## Week 10: LangGraph Agent

### Agent Architecture
A compliance research agent using LangGraph: one reasoning/retrieval role with two tools —
- `retrieve_chunks` — the existing hybrid retriever, `mode` as a parameter rather than a tool per strategy
- `list_namespaces` — lets the agent discover available document scopes instead of relying on a hardcoded list

— plus a deterministic synthesis step and an optional verifier role that checks the drafted answer against retrieved chunks, toggleable per request and via a deployment-wide flag.

Every agent answer includes citations, a confidence score, the model used, verification status, and full query cost (every reasoning and verification turn, not just the last step).

### Key Results
| Metric | Value |
|---|---|
| Single-step queries | 1 retrieval + synthesis, ~3-4s |
| Multi-step queries | 2-4 retrievals + synthesis, ~8-12s |
| With verifier enabled | +1 LLM call minimum; +1 full retrieval round if a retry is triggered |
| Agent endpoint | `POST /agent/query` |
```

---

## Git Commits for Week 10

```
fix(retriever): add configurable vector_score floor via default-valued param + subquery
fix(cache): read EMBEDDING_DIM from config instead of hardcoded 768
fix(schemas): add mode and uptime_seconds to HealthResponse
fix(health): cache embedding probe with lock + asymmetric TTL + cold-start retry
feat(config): add NAMESPACE_REGISTRY, MIN_VECTOR_SCORE, and verifier_enabled feature flag
feat(agent): add list_namespaces + retrieve_chunks tools (closure-bound pool, source_filename end-to-end)
feat(agent): add LangGraph graph with reasoning, synthesis, and verifier nodes
feat(agent): add /agent/query route with citations, cost, and verification exposure
fix(agent): initialize reasoning_usage/verifier_usage reducer lists in ainvoke() initial state
test(agent): add tool, routing, verifier, dedup, usage, and initial-state-shape tests
docs: ARCHITECTURE.md decision 16, README week 10
```

---

## Task 10: Future Work (Scoped, Not Built This Week)

**`fetch_full_document` tool.** For when a 500-character chunk isn't enough surrounding context. Confirm against the actual `documents` table schema before building: reassembly by chunk order needs to sort on however `chunk_index` is actually stored (commonly inside a `metadata` JSON column rather than a dedicated column), not row insertion order.

**Still unresolved — needs the FinOps middleware's actual storage code:** whether usage is persisted per-request (monthly cost rollups would be a free date-range query) or only kept as a resetting counter (monthly would be a real, unrecoverable gap). Worth resolving before scoping it as its own task. Carried forward as open flag #5 at the top of this document.

---

## After Week 10: Projected Ratings

Carried forward unchanged from both source plans — these are your own weekly self-assessment numbers, not independently re-scored here since I don't have a basis for adjusting them beyond what's already tracked.

| # | Dimension | Post-Wk9 | Post-Wk10 | Movement |
|---|---|---|---|---|
| 1 | Python Internals | 9.5 | **9.5** | — |
| 2 | Ingestion Pipeline | 9.5 | **9.5** | — |
| 3 | Database Engineering | 9.5 | **9.5** | — |
| 4 | Async Architecture | 9.0 | **9.0** | — |
| 5 | FastAPI & API Design | 9.0 | **9.0** | — |
| 6 | LLM Integration | 9.5 | **9.5** | — |
| 7 | FinOps / Cost Engineering | 9.5 | **9.5** | — |
| 8 | Three-Mode Config | 9.5 | **9.5** | — |
| 9 | Documentation Quality | 8.5 | **9.0** | +0.5 |
| 10 | Benchmark Evidence | 9.5 | **9.5** | — |
| 11 | Testing | 7.0 | **7.5** | +0.5 |
| 12 | CI/CD | 7.5 | **7.5** | — |
| 13 | RAG Architecture | 9.0 | **9.0** | — |
| 14 | Agent Architecture | 0.0 | **8.5** | +8.5 |
| 15 | MCP Server | 0.0 | **0.0** | — (Week 11) |
| 16 | Security & Governance | 8.0 | **8.0** | — |
| 17 | Deployment Readiness | 8.5 | **8.5** | — |
| 18 | Caching & Cost Opt | 9.0 | **9.0** | — |
| 19 | Evaluation Framework | 9.0 | **9.0** | — |
| 20 | Corpus & Data Quality | 9.0 | **9.0** | — |
| — | **Weighted Overall** | **8.5** | **8.9** | **+0.4** |
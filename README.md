# ai-platform

Production grade AI backend platform built around memory-efficient ingestion, async HTTP, and eventually hybrid RAG retrieval with LangGraph agents.

Core idea: most AI pipelines fail at scale not because of the model, but because of poor infrastructure - loading files eagerly into memory, firing unbounded concurrent requests, or writing everything to disk at once. This project builds the infrastructure layer that handles all of that correctly.

This is a 12-week structured learning project. Each lab isolates one concept, breaks it, measures it, fixes it, then integrates it into the platform. Code in `core/` is production-ready - scripts in `scripts/` show how it was built and tested.

---

## Prerequisites

- Python 3.11+
- Poetry
- Docker Desktop (with WSL 2 backend on Windows)

---

## Getting Started
```bash
# clone and enter
git clone <repo-url>
cd ai-platform

# install dependencies
poetry install

# activate shell
poetry shell

# run any lab script
python scripts/lab_2.5_integration_test.py
```

> **Note:** Scripts import from `core.*`, which needs project root on `PYTHONPATH`.
> If you get `ModuleNotFoundError`, run:
> ```bash
> export PYTHONPATH=$PYTHONPATH:.
> ```

---

## Project Structure
```
core/
├── clients/
│   └── async_http_client.py   # async HTTP with retries, semaphore, timeout
├── database/
│   ├── pool.py                # asyncpg connection pool with pgvector
│   ├── bulk_ops.py            # COPY-based bulk insert
│   └── schema.sql             # documents table definition
├── ingestion/
│   ├── readers.py             # lazy file chunk generator
│   ├── processors.py          # text cleaning generator
│   └── embedders.py           # embedding generator (768-dim)
└── pipeline/
    ├── async_ingest.py        # HTTP-based async ingestion (Week 2)
    └── db_ingest.py           # database-backed ingestion (Week 3)
```

---

## Key Results

| Lab | What is Proved | Result |
|-----|---------------|--------|
| 1.1 | `range` vs `list` memory | 381 MB → 0.0001 MB |
| 1.3 | Chunk iterator memory | 13,000× reduction |
| 1.4 | Generator pipeline memory | 4,800× reduction |
| 2.3 | Semaphore vs unbounded | 100% vs 57% success |
| 2.5 | Async pipeline memory | Constant at any file size |
| 3.3 | COPY vs row-by-row INSERT | 226× faster (102K rows/s) |
| 3.4 | Connection pooling | 1.6× faster, zero overhead |
| 4.1 | GIL limits CPU-bound threading | Threads ≈ Sequential, Processes ≈ 4x faster |
| 4.2 | Serialization break-even point | Sequential wins <1MB, Processes win >10MB (2.44x at 10MB) |
| 4.3 | Event loop responsiveness | Naive: 545ms avg delay → Hybrid: 2.58ms avg delay (2.53x pipeline speedup) |
| 6.2 | Semantic vs string cache hit rate | 41% → 74% on 100-query test set |
| 6.5 | End-to-end cost reduction via cache | ~60% cost reduction |
| 7.3 | Vector vs BM25 vs Hybrid precision | 0.17 / 0.16 / 0.17 Precision@5 — corpus ceiling is 0.20 |
| 7.5 | Reranker answer relevancy lift | +0.12 (0.7983 → 0.9167) with event loop max gap 11ms |

---

## Week 1: Memory-Efficient Ingestion

### Lab 1.1 — Memory Experiments
Proved lazy evaluation (`range`) saves massive memory vs eager loading (`list`). This prevents OOM errors in pipelines.

### Lab 1.2 — Memory Leaks
Learned how circular references bypass Python's reference counting and how garbage collection fixes leaks.

### Lab 1.3 — File Chunk Iterator
Built production iterator/context manager to process huge files with O(1) memory usage.

### Lab 1.4 — Generator Pipeline
Built generator pipeline for massive datasets with constant memory usage.

### Lab 1.5 — Integration Test
Integrated all Week 1 modules and tested end-to-end.

---

## Week 2: Async HTTP & Concurrency

### Lab 2.1 — Event Loop Deep Dive
Explored asyncio event loop, proved it's single-threaded, understood how it handles concurrency without threads.

### Lab 2.2 — Concurrency Trap
Found what happens when you fire too many concurrent requests. Key finding: over-concurrency kills performance.

### Lab 2.3 — Controlled Concurrency
In Lab 2.2, 1000 unbounded requests = 57% success rate. With `Semaphore(500)` = 100% success at same throughput (95 req/s vs 90 req/s). Controlled concurrency wins.

### Lab 2.4 — Production HTTP Client
Built `AsyncHttpClient` - handles thousands of API calls with automatic retries, semaphore rate limiting, and error handling.

### Lab 2.5 — Integration Pipeline
Combined Week 1 + Week 2 into full async pipeline: read → clean → batch → embed → store. Generator chain keeps memory constant regardless of file size. Concurrency drives throughput, memory scales with concurrency not file size.

---

## Week 3: PostgreSQL + pgvector

### Lab 3.1 — Database Setup
Set up PostgreSQL + pgvector via Docker. Connected with psycopg2 (sync) first, then asyncpg (async). Registered pgvector extension and created vector(768) schema.

### Lab 3.2 — Row-by-Row vs Bulk Insert
Benchmarked three psycopg2 approaches. `executemany` is a lie (1.03x). `execute_batch` gives 2.27x. Both still too slow for production.

### Lab 3.3 — asyncpg COPY
asyncpg's `copy_records_to_table()` hit 102,106 rows/s — a 226x speedup over row-by-row. COPY bypasses SQL parsing entirely.

### Lab 3.4 — Connection Pooling + Integration
Built `asyncpg.create_pool()` with `init=register_vector`. Pool concurrent (0.63s) beats fresh-connect-per-batch (0.99s). Integrated everything into `db_ingest.py`: read → clean → embed → COPY to postgres. 1,297 chunks/sec, all rows verified in DB.

---
## Week 4: GIL, Multiprocessing & Hybrid Concurrency

### Lab 4.1 — GIL Proof

Proved the GIL prevents parallel execution for CPU-bound threads. Four threads running sum(i*i for i in range(5M)) takes the same time as sequential. Four processes take ~4x less. The fix for CPU-bound work is ProcessPoolExecutor, not ThreadPoolExecutor.

### Lab 4.2 — Serialization Overhead

Every process boundary has a pickle cost. Found the break-even: sequential wins below ~1MB-10MB of data per task, processes win above ~10MB. Small tasks (DB writes, tiny cleanups) should never use multiprocessing — the overhead dominates. Large tasks (embedding batches, chunking large docs) benefit from it.

### Lab 4.3 — Hybrid Async + Multiprocessing

Proved that CPU work called directly inside an async coroutine blocks the entire event loop — average 545ms delay, nothing else can run. run_in_executor() offloads CPU work to a process pool while immediately returning control to the event loop. Result: 2.58ms average delay, 2.53x pipeline speedup. This is the production pattern for core/pipeline/.

## Week 5: RAG API & Structured Outputs

### Lab 5.1 — The FastAPI LIFO Onion
Built the API layer with robust middlewares. Proved that FastAPI mounts middleware in Last-In-First-Out (LIFO) order, and fixed our `FinOpsMiddleware` by strictly ordering it after the Request ID generation.

### Lab 5.2 — LiteLLM Abstraction
Replaced raw provider SDKs with LiteLLM. Moving between local Ollama and production GPT-4o is now a single config change without rewriting the core `acompletion` logic.

### Lab 5.3 — Structured Pydantic Outputs
Forced the LLM into returning a strict `GeneratedAnswer` schema to eliminate regex parsing. Eradicated silent database corruption by catching hallucinations loudly at the Pydantic validation boundary.

### Lab 5.4 — Math & Mislabeled Files
Updated the vector search to use Cosine Distance (`<=>`) for accurate similarity scoring (`1.0 - distance`), and bulletproofed the chunker routing against mislabeled or unknown file extensions.

---

## Week 6: Caching & Cost Optimization

### Lab 6.1 — Cache-Aside with Redis
Built exact-match Redis caching: hash the query + namespace + top_k → check Redis first, only hit the DB and LLM on a miss. Cache hit returns in ~1ms vs ~800ms full pipeline.

### Lab 6.2 — Semantic Caching
Exact match only catches identical queries. Added a Redis HNSW vector index: embed the query, find the nearest cached query by cosine similarity, return the cached answer if similarity > 0.95. Hit rate went from 41% to 74% on the test set. The key insight: you need the embedding for vector search anyway, so the semantic cache check costs nothing extra.

### Lab 6.3 — Model Routing by Query Complexity
Not every query needs the most expensive model. A word count + keyword heuristic routes short factual queries to the cheap model and longer analytical queries to the full model. Measured cost per 100 mixed queries before and after.

### Lab 6.4 & 6.5 — Integration & Benchmark
Wired all three layers (exact cache → semantic cache → full pipeline) into the search route. Dual-layer cache reduces LLM calls by ~60% on a realistic query distribution. Benchmark committed to `benchmarks/lab_6.5_cache_benchmarks.json`.

---

## Week 7: Hybrid RAG & Evaluation

### Lab 7.1 — Vector Search Failure Cases
Documented 5 concrete failure modes of pure vector search on the legal compliance corpus. Article numbers drift (searching "Article 5" returns "Article 6" content). Rare identifiers like section numbers compress into generic topics. Negation is invisible to cosine similarity. These aren't theoretical — all five were reproduced with actual queries against the real database.

### Lab 7.2 — FTS Index Migration
Added a `tsvector` full-text search column to the documents table and a GIN index. Migrated the schema and verified BM25 scoring works via `ts_rank()`.

### Lab 7.3 — Hybrid Retrieval (RRF)
Built the hybrid retriever: run BM25 and vector search in parallel, merge by Reciprocal Rank Fusion (k=60). Neither retriever dominates — documents scoring well in either list get a boost. Also discovered the AND/OR threshold problem: PostgreSQL's `plainto_tsquery` uses AND by default, which returns empty results for long natural language queries. Fixed with `BM25_OR_THRESHOLD = 5` — queries under 5 words use AND (precision mode), 5+ words rewrite to OR (recall mode).

Precision@5 results across 20 manually labeled queries (corpus ceiling is 0.20 = 1 relevant chunk per query in top 5):

| Mode | Precision@5 | Notes |
|---|---|---|
| Vector only | 0.17 | Fails on exact terms, article numbers |
| BM25 only | 0.16 | Fails on semantic paraphrases |
| Hybrid RRF | 0.17 | Captures both — 85% hit rate at the ceiling |

### Lab 7.5 — Cross-Encoder Reranking + Eval
Added a two-stage pipeline: hybrid RRF produces up to 20 candidates, cross-encoder (`ms-marco-MiniLM-L-6-v2`) re-scores them by reading query+chunk together and picks the top 5. Answer relevancy went from 0.7983 to 0.9167 (+0.12).

Before enabling this in the async API, ran an event-loop safety check (Lab C.5): confirmed that when reranking is offloaded via `run_cpu_bound()`, the event loop heartbeat max gap is 11ms — well under the 20ms safe threshold. `rerank=True` is now the production default.

Evaluation was run with DeepEval using Gemini-2.5-pro as the judge:

| Metric | Hybrid RRF | Hybrid + Reranked |
|---|---|---|
| Faithfulness | 0.9500 | 0.9667 |
| Answer Relevancy | 0.7983 | **0.9167** |
| Context Precision | 0.3917 | 0.3833 |
| Context Recall | 0.4000 | 0.4000 |

Context recall ceiling at 0.40 is a corpus gap, not a retriever bug — 6 of 10 eval questions ask for content not present in the ingested documents. Dataset expansion is the next step.

---

## What's Next

- **Week 8: Governance & Data Ops** — Namespace isolation, document lifecycle with SHA-256 hash-based staleness detection, audit log, rate limiting, token budgets, and Microsoft Fabric batch ingestion.
- Weeks 9–12: Containerization, CI/CD, LangGraph agents, MCP server, feedback loop, GitHub webhook connector.
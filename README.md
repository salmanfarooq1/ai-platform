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

## What's Next

- **Week 6: Caching & Redis** — Implementing Cache-Aside and Semantic Caching to eliminate redundant LLM calls and reduce API spend.
- Weeks 7–12: LangGraph agents, hybrid RAG retrieval, evals with RAGAS, production deployment.
# ai-platform

Production grade AI backend platform built around memory-efficient ingestion, async HTTP, and eventually hybrid RAG retrieval with LangGraph agents.

Core idea: most AI pipelines fail at scale not because of the model, but because of poor infrastructure - loading files eagerly into memory, firing unbounded concurrent requests, or writing everything to disk at once. This project builds the infrastructure layer that handles all of that correctly.

This is a 12-week structured learning project. Each lab isolates one concept, breaks it, measures it, fixes it, then integrates it into the platform. Code in `core/` is production-ready - scripts in `scripts/` show how it was built and tested.

---

## Prerequisites

- Python 3.11+
- Poetry

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
├── ingestion/
│   ├── readers.py             # lazy file chunk generator
│   ├── processors.py          # text cleaning generator
│   └── embedders.py           # embedding helpers
└── pipeline/
    └── async_ingest.py        # end-to-end async ingestion
```

---

## Key Results

| Lab | What I Proved | Result |
|-----|---------------|--------|
| 1.1 | `range` vs `list` memory | 381 MB → 0.0001 MB |
| 1.3 | Chunk iterator memory | 13,000× reduction |
| 1.4 | Generator pipeline memory | 4,800× reduction |
| 2.3 | Semaphore vs unbounded | 100% vs 57% success |
| 2.5 | Async pipeline memory | Constant at any file size |

---

## Week 1: Memory-Efficient Ingestion

Full notes: [`docs/week1_learnings.md`](docs/week1_learnings.md)

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

Full notes: [`docs/week2_learnings.md`](docs/week2_learnings.md)

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

## What's Next

Week 3: Vector embeddings and storage (pgvector/Pinecone integration)

Week 4: Basic RAG retrieval pipeline

Weeks 5-12: LangGraph agents, hybrid retrieval, production deployment
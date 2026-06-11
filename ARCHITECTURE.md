# Architecture Decisions

## Decision 1: run_in_executor for CPU-Bound Work (Week 4)
**Context:** FastAPI is single-threaded async. CPU-heavy functions block the event loop.
**Problem:** Calling chunkers or embedding preprocessing directly in a route handler
             freezes all other requests for the duration.
**Solution:** `core/processing/cpu_offload.run_cpu_bound()` — wraps any callable in
             `loop.run_in_executor(ProcessPoolExecutor)`. Event loop stays free.
**Trade-off:** Process pool has fixed spawn cost. Only worth it for tasks >~10ms of CPU.
             Small tasks (DB writes, JSON parsing) stay as plain awaits.

## Decision 2: Domain-Specific Chunking Strategy (Week 4)
**Context:** Generic recursive chunking treats API docs the same as prose text.
**Problem:** OpenAPI specs have natural semantic boundaries at the endpoint level.
             Splitting across endpoints breaks retrieval for "how do I call X?" queries.
**Solution:** CHUNKER_REGISTRY dispatches by file extension:
               .txt/.md → recursive/header-aware split
               .json    → chunk_openapi_spec (one operation = one chunk)
**Trade-off:** Must detect document type at ingestion time via file extension.
**AIDA application:** AIDA ingests API documentation — endpoint-level chunking
             improves retrieval quality for "how do I call endpoint X?" queries.
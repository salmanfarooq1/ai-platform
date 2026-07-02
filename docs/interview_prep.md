# AI Platform — Systems Design Interview Prep

This document captures the hardcore engineering defenses for the architectural decisions made in this project. It is designed to prepare you for 2026/2027 Senior AI Engineering interviews.

---

## 1. The Semaphore vs Unbounded Concurrency Trap
**Interviewer:** "Why did you use an `asyncio.Semaphore(500)` in your HTTP client instead of just firing off `asyncio.gather()` for all 10,000 requests?"

**Your Defense:** 
"If we fire 10,000 unbounded requests using `asyncio.gather`, the event loop will immediately open 10,000 sockets. This leads to **socket exhaustion** (running out of ephemeral ports or hitting the OS file descriptor limit) and **target server DOS**. In my load testing, unbounded requests resulted in a 57% success rate because the OS dropped connections. By applying a Semaphore of 500, we act as a bouncer, guaranteeing that only 500 requests are 'in flight' at a given millisecond. This achieved a 100% success rate without sacrificing overall throughput."

## 2. Python's GIL & CPU-Bound Work in Async
**Interviewer:** "FastAPI is single-threaded async. What happens if 10 users hit the `/ingest` endpoint simultaneously, and your chunking algorithm takes 2 seconds of CPU time per document?"

**Your Defense:**
"If we run the chunking synchronously inside the route handler, the event loop freezes for 20 seconds. During that time, the API cannot accept new connections or process pending I/O. The GIL completely locks the thread. 
To solve this, I used a **Hybrid Concurrency Model**. I wrapped the CPU-bound chunking logic in `loop.run_in_executor()` backed by a `ProcessPoolExecutor`. This completely bypasses the GIL by sending the CPU work to a separate OS process, freeing the event loop to instantly return to handling other users' I/O requests. My profiling proved this reduced event loop delay from 545ms to 2.5ms."

## 3. The PostgreSQL Exact Nearest Neighbor Cliff
**Interviewer:** "You used pgvector. What happens when your `documents` table hits 10 million rows? Won't `ORDER BY embedding <=> query_vector` take 5 seconds?"

**Your Defense:**
"Yes, exact nearest neighbor (k-NN) requires a sequential scan calculating the distance for every single row. It scales linearly $O(N)$ and falls off a performance cliff around 1-5 million rows. 
To fix this in production, we implement an **HNSW (Hierarchical Navigable Small World)** index. HNSW builds a graph layer that allows for Approximate Nearest Neighbor (ANN) search. It trades a slight drop in exact recall accuracy for logarithmic $O(log N)$ search time. Additionally, I partitioned the table by `namespace`, which acts as a massive pre-filter before the vector search even begins."

## 4. Memory Leaks & Circular References
**Interviewer:** "How does Python handle memory management? If you have a memory leak in a long-running pipeline, where do you look first?"

**Your Defense:**
"Python uses Reference Counting as its primary memory management. When a variable's ref count hits 0, it's immediately destroyed. However, if Object A points to Object B, and Object B points back to A, they form a **circular reference**. Their ref counts will never hit 0, even when they go out of scope. 
This is why Python has a secondary Garbage Collector (GC), which specifically hunts for circular references. If I see a memory leak, I first check if we are creating large cyclical data structures, and I verify that we haven't accidentally disabled the GC (which is sometimes done in latency-critical production apps to avoid GC pause times)."

## 5. Generator Pipelines for O(1) Memory
**Interviewer:** "If a user uploads a 100GB log file, how does your ingestion pipeline prevent Out-Of-Memory (OOM) crashes?"

**Your Defense:**
"The entire ingestion pipeline is built using **generators (yield)** instead of eager loading (lists). We never load the entire file into memory. We yield one chunk, clean that chunk, embed that chunk, and stream it to the database. The memory profile of our pipeline remains $O(1)$ constant, strictly bounded by our batch size (e.g., 50 chunks at a time), regardless of whether the file is 1MB or 100GB."

## 6. Reducing LLM Costs in Production
**Interviewer:** "How do you reduce LLM costs in production?"

**Your Defense:**
"To drastically reduce LLM costs without sacrificing quality, we implement a layered cost-optimization stack. 
First, we use an **Exact Cache** (O(1) Redis lookup) to instantly return answers for identical queries at $0 cost. 
Second, we deploy a **Semantic Cache** using Redis HNSW vectors to catch paraphrased queries (e.g., 'What is AI?' vs 'Explain AI'). Because users rarely ask the same question the exact same way, the semantic cache pushes our hit rate from around 40% up to 60-70%. 
Finally, for all remaining cache misses, we use **Model Routing**. A lightweight classifier evaluates query complexity, routing simple factual lookups to cheap, fast models (like local Qwen2.5 or Llama 8B) and reserving expensive models (like GPT-4o) solely for complex reasoning tasks. By stacking these three layers, we bypass the LLM entirely for most queries and minimize the cost of the ones that do get through."

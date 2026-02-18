# ai-platform
A production-ready AI backend platform with memory-efficient RAG ingestion, hybrid retrieval, and LangGraph agents.

## Week 1 Learnings 

[see `docs/week1_learnings.md`](docs/week1_learnings.md) for detailed learnings.

* **Lab 1.1 - Memory Experiments:** 
    Demonstrated memory savings of lazy evaluation (`range`) over eager loading (`list`) to prevent pipeline OOM errors.
* **Lab 1.2 - Memory Leak Experiments:** 
    Investigated how circular references bypass reference counting and how to mitigate leaks using garbage collection.
* **Lab 1.3 - File Chunk Iterator:** 
    Built a production-ready iterator/context manager to process massive datasets with constant $O(1)$ memory usage.
* **Lab 1.4 - Generator Pipeline:** 
    Built a production-ready generator pipeline to process massive datasets with constant $O(1)$ memory usage.
* **Lab 1.5 - Module Integration Test:** 
    Integrated all the modules from the previous labs into a single pipeline and tested it.

## Week 2 Learnings

[see `docs/week2_learnings.md`](docs/week2_learnings.md) for detailed learnings.

* **Lab 2.1 - Event Loop Deep Dive:** 
    Explored the asyncio event loop, proved it's single-threaded, and understood how it handles concurrency.
* **Lab 2.2 - Concurrency Trap:** 
    Investigated the concurrency trap and understood the key point "*over concurrency HURTS performance*".
* **Lab 2.3 - Controlled Concurrency:** 
    In Lab 2.2, we saw 1000 concurrent requests fail with 57% success. By using Semaphore(500), we achieved 100% success with nearly identical throughput (95 req/s vs 90 req/s), proving controlled concurrency is superior to unbounded.
* **Lab 2.4 - Production-Ready Async HTTP Client:** 
    Production async HTTP client - handles 1000s of API calls with automatic retries, rate limiting, and graceful error handling
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

# Week 6 Learnings: Caching, Model Routing, and Cost Optimization

## Core Concepts Mastered
1. **Dual-Layer Caching:**
   - **Exact Cache:** O(1) key-value lookup in Redis for identical queries. Perfect for predictable repeat traffic, achieving ~40% hit rates.
   - **Semantic Cache:** Vector similarity search using RediSearch (HNSW index) to catch paraphrased queries ("How do I delete data?" vs "What is the right to erasure?"). This pushes hit rates to 60-70%, completely bypassing the LLM step for the majority of user traffic.

2. **Model Routing:**
   - LLMs are not one-size-fits-all. GPT-4o is expensive and powerful; smaller models (like Llama 3 8B or Qwen 2.5) are cheap and fast.
   - We implemented a heuristic classifier to determine query complexity. Simple factual lookups are routed to the fallback model, while analytical/comparative queries are routed to the primary massive model. This achieves a balance between top-tier reasoning and cost efficiency.

3. **Graceful Degradation:**
   - Caches are ephemeral by nature. We architected the `/search` endpoint to catch `RedisError` exceptions. If Redis goes down, the API doesn't crash; it gracefully degrades to a cache miss, processing the full vector search and LLM generation so the user experience is uninterrupted.

## Tools & Libraries Used
- **Redis Stack:** Used for both standard key-value exact caching and `FT.SEARCH` HNSW vector similarity for semantic caching.
- **LiteLLM:** A standard proxy library that allowed us to switch between OpenAI, Groq, and local Ollama models with zero code changes—just by changing configuration prefixes (e.g., `groq/meta-llama/...`).
- **HTTPX:** Used `httpx.AsyncClient` for robust asynchronous integration testing of our HTTP endpoints.

## Production Best Practices
- **Atomic Operations:** When caching, use `SET key value EX seconds` as a single atomic operation rather than setting the key and then applying an expiry. This prevents memory leaks if the process crashes between commands.
- **FinOps Tracking:** We injected `X-Cost-USD`, `X-Cache`, and `X-Cache-Type` headers directly into our HTTP responses. This allows API gateways and telemetry dashboards to passively track financial savings and cache hit rates in real time.

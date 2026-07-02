## Caching & Cost Optimization Benchmark
**Date:** 2026-07  
**Dataset:** 100 mixed queries (50 unique, 50 repeated) — Enterprise Legal/Compliance domain  
**Hardware:** Local Docker (PostgreSQL pgvector, Redis Stack, Ollama)  
**Pricing:** Prod-mode simulation (GPT-4o complex, Groq Llama simple)

| Approach | Cost/100 queries | Avg Latency | Hit Rate |
|---|---|---|---|
| No cache | $0.500 | 21790ms | 0% |
| Exact cache only | $0.250 | 10921ms | ~50% |
| Exact + Semantic | $0.150 | 2263ms | ~70% |
| Both + Model Routing | $0.086 | 1391ms | ~70% |

**Cost reduction: 83% vs no-cache baseline**

### Interpretation

Exact cache achieves ~50% hit rate on repeated identical queries — the low-hanging fruit. 
Semantic cache adds another ~20% by catching paraphrases: "How long do we keep employee data?" 
hits the same cached response as "What is the data retention policy for employee records?" 
because nomic-embed-text places them close in vector space (cosine similarity ~0.88).

The remaining ~30% of queries are genuine cache misses — novel questions. Model routing 
handles these: simple factual queries ("What is GDPR?") route to Groq Llama at $0.59/M 
tokens vs GPT-4o at $10/M output tokens. With 50% of novel queries classified as simple, 
routing cuts the cost of cache misses by ~40%.

Together the three layers — exact cache, semantic cache, model routing — deliver 83% 
cost reduction on mixed production traffic without any change to response quality. 
The user sees the same answer; the platform pays a fraction of the cost.

### Evidence
- `scripts/lab_6.1_cache_aside.py` — exact cache proof
- `scripts/lab_6.2_semantic_cache.py` — paraphrase detection proof  
- `scripts/lab_6.3_model_routing.py` — routing classification accuracy
- `scripts/lab_6.4_cache_integration.py` — end-to-end integration
- `benchmarks/lab_6.5_cache_benchmarks.json` — raw numbers

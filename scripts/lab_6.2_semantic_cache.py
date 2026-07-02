"""
Lab 6.2: Semantic Cache — Paraphrase detection via embedding similarity.

Domain: Enterprise Legal/Compliance documentation.
Real queries an employee might ask a compliance RAG system.

Tests:
1. Store canonical queries, test paraphrases → expect HITs
2. Test unrelated queries → expect MISSes  
3. Compare exact vs semantic hit rate on 50 mixed queries
4. Benchmark: latency and simulated cost savings
"""

import asyncio
import time
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.cache import (
    get_redis,
    close_redis,
    create_semantic_cache_index,
    embed_query,
    semantic_cache_lookup,
    semantic_cache_store,
    get_cached_response,
    set_cached_response,
    SEMANTIC_CACHE_THRESHOLD,
)


# --- Realistic legal/compliance domain data ---

# Each entry: (canonical_query, paraphrases, unrelated_queries)
COMPLIANCE_SCENARIOS = [
    {
        "canonical": "What is the data retention policy for employee records?",
        "paraphrases": [
            "How long do we keep employee data?",
            "What are the rules for retaining staff records?",
            "Employee record retention requirements",
        ],
        "unrelated": [
            "How do I submit a travel expense report?",
            "What is the office wifi password?",
        ],
    },
    {
        "canonical": "What is the process for reporting a data breach?",
        "paraphrases": [
            "How do I report a security incident involving personal data?",
            "Steps to follow when customer data is compromised",
            "Data breach notification procedure",
        ],
        "unrelated": [
            "When is the next company all-hands meeting?",
            "How do I request parental leave?",
        ],
    },
    {
        "canonical": "What are the GDPR requirements for user consent?",
        "paraphrases": [
            "How must we obtain consent under GDPR?",
            "GDPR consent requirements for data processing",
            "What does GDPR say about user consent?",
        ],
        "unrelated": [
            "What is the company dress code policy?",
            "How do I reset my corporate password?",
        ],
    },
]

# Simulated response — in production this comes from your RAG pipeline
def fake_compliance_response(query: str) -> dict:
    return {
        "query": query,
        "results": [{
            "content": f"Compliance answer for: {query}",
            "document_id": "compliance-handbook-v3",
            "score": 0.92,
        }],
        "total_results": 1,
        "model_used": "qwen2.5:latest",
        "cost_usd": 0.0031,
    }


# --- Test 1: Paraphrase detection ---
async def calibrate_threshold():
    import numpy as np
    print("\n=== Threshold Calibration ===")
    
    for scenario in COMPLIANCE_SCENARIOS:
        canonical = scenario["canonical"]
        canonical_emb = await embed_query(canonical)
        
        print(f"\n  Canonical: '{canonical[:60]}'")
        
        for para in scenario["paraphrases"]:
            para_emb = await embed_query(para)
            a = np.array(canonical_emb, dtype=np.float32)
            b = np.array(para_emb, dtype=np.float32)
            similarity = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            print(f"    {similarity:.4f} — '{para[:55]}'")
        
        for unrelated in scenario["unrelated"]:
            unrelated_emb = await embed_query(unrelated)
            a = np.array(canonical_emb, dtype=np.float32)
            b = np.array(unrelated_emb, dtype=np.float32)
            similarity = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
            print(f"    {similarity:.4f} — [UNRELATED] '{unrelated[:45]}'")

async def test_paraphrase_detection():
    print("\n=== Test 1: Paraphrase Detection ===")
    results = []

    for scenario in COMPLIANCE_SCENARIOS:
        canonical = scenario["canonical"]
        print(f"\n  Seeding: '{canonical[:60]}...'")

        # Embed and store canonical query
        embedding = await embed_query(canonical)
        response = fake_compliance_response(canonical)
        await semantic_cache_store(canonical, "legal", embedding, response)

        # Test paraphrases — should HIT
        for para in scenario["paraphrases"]:
            para_embedding = await embed_query(para)
            hit = await semantic_cache_lookup(para, "legal", para_embedding)
            status = "HIT  ✓" if hit else "MISS ✗"
            print(f"    {status} '{para[:60]}'")
            results.append(("paraphrase", hit is not None))

        # Test unrelated — should MISS
        for unrelated in scenario["unrelated"]:
            unrelated_embedding = await embed_query(unrelated)
            hit = await semantic_cache_lookup(unrelated, "legal", unrelated_embedding)
            status = "MISS ✓" if not hit else "HIT  ✗ (FALSE POSITIVE)"
            print(f"    {status} '{unrelated[:60]}'")
            results.append(("unrelated", hit is None))

    para_hits = sum(1 for t, r in results if t == "paraphrase" and r)
    para_total = sum(1 for t, _ in results if t == "paraphrase")
    unrelated_correct = sum(1 for t, r in results if t == "unrelated" and r)
    unrelated_total = sum(1 for t, _ in results if t == "unrelated")

    print(f"\n  Paraphrase hit rate  : {para_hits}/{para_total} ({para_hits/para_total*100:.0f}%)")
    print(f"  False positive rate  : {unrelated_total - unrelated_correct}/{unrelated_total} ({(unrelated_total-unrelated_correct)/unrelated_total*100:.0f}%)")
    return para_hits, para_total


# --- Test 2: Exact vs Semantic cache hit rate comparison ---
async def test_cache_comparison():
    print("\n=== Test 2: Exact vs Semantic Cache Hit Rate (50 queries) ===")

    # 25 unique canonical + 25 paraphrases
    queries = []
    for scenario in COMPLIANCE_SCENARIOS:
        queries.append(("canonical", scenario["canonical"]))
        for p in scenario["paraphrases"]:
            queries.append(("paraphrase", p))

    # Pad to 50 with repeated canonicals
    while len(queries) < 50:
        for scenario in COMPLIANCE_SCENARIOS:
            queries.append(("canonical", scenario["canonical"]))
            if len(queries) >= 50:
                break

    exact_hits, semantic_hits, total = 0, 0, 0

    for query_type, query in queries[:50]:
        total += 1

        # Check exact cache
        exact = await get_cached_response(query, "legal", 5)
        if exact:
            exact_hits += 1

        # Check semantic cache
        embedding = await embed_query(query)
        semantic = await semantic_cache_lookup(query, "legal", embedding)
        if semantic:
            semantic_hits += 1

    print(f"  Total queries    : {total}")
    print(f"  Exact hits       : {exact_hits} ({exact_hits/total*100:.1f}%)")
    print(f"  Semantic hits    : {semantic_hits} ({semantic_hits/total*100:.1f}%)")
    print(f"  Semantic uplift  : +{semantic_hits - exact_hits} queries served from cache")


# --- Test 3: Latency benchmark ---
async def test_latency():
    print("\n=== Test 3: Latency — Semantic lookup vs full pipeline ===")

    query = "What are the legal requirements for data retention?"
    embedding = await embed_query(query)

    # Semantic lookup latency
    latencies = []
    for _ in range(10):
        start = time.perf_counter()
        await semantic_cache_lookup(query, "legal", embedding)
        latencies.append((time.perf_counter() - start) * 1000)

    avg_lookup = sum(latencies) / len(latencies)

    # Simulated full pipeline latency (embedding + DB search + LLM)
    simulated_pipeline_ms = 850  # realistic: 50ms embed + 300ms search + 500ms LLM

    print(f"  Semantic lookup avg : {avg_lookup:.2f}ms")
    print(f"  Full pipeline (sim) : {simulated_pipeline_ms}ms")
    print(f"  Speedup             : {simulated_pipeline_ms/avg_lookup:.0f}x")
    print(f"  Cost per LLM call   : $0.0031 (qwen2.5)")
    print(f"  Cost per cache hit  : $0.0000")

    return avg_lookup


# --- Save benchmark results ---
async def save_benchmarks(para_hits: int, para_total: int, avg_lookup_ms: float):
    results = {
        "lab": "6.2_semantic_cache",
        "threshold": SEMANTIC_CACHE_THRESHOLD,
        "embedding_model": "ollama/nomic-embed-text",
        "domain": "enterprise_legal_compliance",
        "paraphrase_hit_rate": round(para_hits / para_total, 3),
        "avg_semantic_lookup_ms": round(avg_lookup_ms, 3),
        "simulated_pipeline_ms": 850,
        "speedup_factor": round(850 / avg_lookup_ms, 1),
        "cost_per_llm_call_usd": 0.0031,
        "cost_per_cache_hit_usd": 0.0,
    }

    output_path = Path("benchmarks/lab_6.2_semantic_cache.json")
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\n[benchmark] Saved to {output_path}")


# --- Cleanup ---
async def flush_semantic_keys():
    r = await get_redis()
    keys = await r.keys("semcache:*")
    if keys:
        await r.delete(*keys)
    print(f"[cleanup] Flushed {len(keys)} semantic cache keys")


async def main():
    print("Lab 6.2: Semantic Cache — Enterprise Legal/Compliance Domain")
    print(f"Similarity threshold : {SEMANTIC_CACHE_THRESHOLD}")

    r = await get_redis()
    await r.ping()
    print("Redis connection     : ok")

    await create_semantic_cache_index()

    await calibrate_threshold()

    para_hits, para_total = await test_paraphrase_detection()
    await test_cache_comparison()
    avg_lookup = await test_latency()
    await save_benchmarks(para_hits, para_total, avg_lookup)
    await flush_semantic_keys()

    await close_redis()
    print("\nLab 6.2 complete.")


if __name__ == "__main__":
    asyncio.run(main())

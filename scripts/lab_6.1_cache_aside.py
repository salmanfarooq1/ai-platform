"""
Lab 6.1: Cache-Aside Pattern
Proves exact-match caching reduces latency and cost.

Test plan:
1. 20 unique queries → all misses → measure latency
2. Same 20 queries → all hits → measure latency
3. Normalization: "What is AI?" vs "what is ai?" → same hit
4. Whitespace: "What is AI?" vs "What is AI? " → same hit
5. 100 mixed queries (50 unique, 50 repeats) → measure hit rate
"""

import asyncio
import time
import json
import sys
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.cache import (
    get_redis,
    close_redis,
    cache_key,
    get_cached_response,
    set_cached_response,
    CACHE_TTL_SECONDS,
)

# Fake pipeline result simulates what /search would return ---
# In production this is the real search response. Here we fake it
# to isolate cache behavior from DB/LLM latency.
def fake_pipeline_result(query: str) -> dict:
    return {
        "query": query,
        "results": [{"content": f"result for {query}", "score": 0.95}],
        "total_results": 1,
        "model_used": "mock",
    }


# --- Simulate one request: cache-aside logic ---
async def handle_request(query: str, namespace: str, top_k: int) -> tuple[dict, bool, float]:
    """
    Returns (response, was_cache_hit, latency_seconds).
    This is exactly what your /search route will do — check cache,
    miss → run pipeline → store → return.
    """
    start = time.perf_counter()

    cached = await get_cached_response(query, namespace, top_k)
    if cached is not None:
        latency = time.perf_counter() - start
        return cached, True, latency

    # MISS — simulate pipeline (sleep = embedding + DB + LLM latency)
    await asyncio.sleep(0.05)  # 50ms simulated pipeline
    result = fake_pipeline_result(query)
    await set_cached_response(query, namespace, top_k, result)

    latency = time.perf_counter() - start
    return result, False, latency


# --- Test 1 & 2: Miss then Hit on 20 unique queries ---
async def test_miss_then_hit():
    print("\n=== Test 1: 20 unique queries (cold cache) ===")
    queries = [f"what is concept number {i} in machine learning" for i in range(20)]
    namespace, top_k = "test", 5

    miss_latencies = []
    for q in queries:
        _, hit, latency = await handle_request(q, namespace, top_k)
        miss_latencies.append(latency)
        assert not hit, f"Expected miss, got hit for: {q}"

    print(f"  All 20 → MISS ✓")
    print(f"  Avg miss latency : {sum(miss_latencies)/len(miss_latencies)*1000:.2f}ms")
    print(f"  Total miss cost  : simulated $0.002000 (20 × $0.0001)")

    print("\n=== Test 2: Same 20 queries (warm cache) ===")
    hit_latencies = []
    for q in queries:
        _, hit, latency = await handle_request(q, namespace, top_k)
        hit_latencies.append(latency)
        assert hit, f"Expected hit, got miss for: {q}"

    print(f"  All 20 → HIT ✓")
    print(f"  Avg hit latency  : {sum(hit_latencies)/len(hit_latencies)*1000:.2f}ms")
    print(f"  Total hit cost   : $0.000000")
    print(f"  Speedup          : {sum(miss_latencies)/sum(hit_latencies):.1f}x")
    
    return miss_latencies, hit_latencies


# --- Charting: Visualize Cache Performance ---
def plot_cache_latency_chart(miss_latencies: list[float], hit_latencies: list[float]):
    """
    Generates a beautiful, light-themed chart comparing Miss vs Hit latencies.
    Saves to scripts/lab_6.1_latency_chart.png.
    """
    print("\n[chart] Generating latency comparison chart...")
    
    # Setup aesthetic light theme
    plt.style.use('bmh')
    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    fig.patch.set_facecolor('#F8F9FA')
    ax.set_facecolor('#FFFFFF')
    
    # Convert to milliseconds
    miss_ms = [l * 1000 for l in miss_latencies]
    hit_ms = [l * 1000 for l in hit_latencies]
    
    x = np.arange(len(miss_ms))
    width = 0.4
    
    # Plot bars
    bars1 = ax.bar(x - width/2, miss_ms, width, label='Cache Miss (DB + LLM)', color='#FF6B6B', alpha=0.9, edgecolor='white')
    bars2 = ax.bar(x + width/2, hit_ms, width, label='Cache Hit (Redis)', color='#4ECDC4', alpha=0.9, edgecolor='white')
    
    # Styling
    ax.set_ylabel('Latency (ms)', fontsize=12, fontweight='bold', color='#333333')
    ax.set_xlabel('Query #', fontsize=12, fontweight='bold', color='#333333')
    ax.set_title('Cache-Aside Performance: Miss vs Hit Latency', fontsize=14, fontweight='bold', color='#2B2D42', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels([str(i+1) for i in x], fontsize=9)
    ax.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    
    # Grid lines
    ax.grid(True, axis='y', linestyle='--', alpha=0.6, color='#E0E0E0')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#E0E0E0')
    ax.spines['bottom'].set_color('#E0E0E0')
    
    # Add annotations for averages
    avg_miss = sum(miss_ms) / len(miss_ms)
    avg_hit = sum(hit_ms) / len(hit_ms)
    ax.axhline(y=avg_miss, color='#FF6B6B', linestyle=':', alpha=0.8)
    ax.axhline(y=avg_hit, color='#4ECDC4', linestyle=':', alpha=0.8)
    
    ax.text(len(x)-1, avg_miss + (max(miss_ms)*0.02), f'Avg: {avg_miss:.1f}ms', color='#FF6B6B', fontweight='bold', ha='right')
    ax.text(len(x)-1, avg_hit + (max(miss_ms)*0.02), f'Avg: {avg_hit:.1f}ms', color='#4ECDC4', fontweight='bold', ha='right')
    
    # Save
    out_path = Path(__file__).parent / "lab_6.1_latency_chart.png"
    plt.tight_layout()
    plt.savefig(out_path, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close()
    
    print(f"  Chart saved successfully to: {out_path.name} ✓")


# --- Test 3: Normalization ---
async def test_normalization():
    print("\n=== Test 3: Query normalization ===")
    namespace, top_k = "test", 5

    # Seed with canonical form
    await set_cached_response("what is ai", namespace, top_k, fake_pipeline_result("what is ai"))

    variants = [
        "What is AI",
        "WHAT IS AI",
        "what is ai",
    ]
    for variant in variants:
        result = await get_cached_response(variant, namespace, top_k)
        status = "HIT ✓" if result else "MISS ✗"
        print(f"  '{variant}' → {status}")


# --- Test 4: Whitespace stripping ---
async def test_whitespace():
    print("\n=== Test 4: Whitespace stripping ===")
    namespace, top_k = "test", 5

    await set_cached_response("what is ai", namespace, top_k, fake_pipeline_result("what is ai"))

    variants = [
        "what is ai  ",
        "  what is ai",
        "  what is ai  ",
    ]
    for variant in variants:
        result = await get_cached_response(variant, namespace, top_k)
        status = "HIT ✓" if result else "MISS ✗"
        print(f"  '{variant}' → {status}")


# --- Test 5: Hit rate on 100 mixed queries ---
async def test_hit_rate():
    print("\n=== Test 5: Hit rate — 100 mixed queries (50 unique, 50 repeats) ===")
    namespace, top_k = "test", 5

    unique = [f"unique query about topic {i}" for i in range(50)]
    # 100 queries: each unique query appears twice (first miss, second hit)
    mixed = unique + unique  # simple 50% repeat rate

    hits, misses = 0, 0
    for q in mixed:
        _, was_hit, _ = await handle_request(q, namespace, top_k)
        if was_hit:
            hits += 1
        else:
            misses += 1

    print(f"  Total requests : 100")
    print(f"  Hits           : {hits}")
    print(f"  Misses         : {misses}")
    print(f"  Hit rate       : {hits/100*100:.1f}%  (expected ~50%)")


# --- Cache key collision test ---
async def test_key_isolation():
    print("\n=== Test 6: Key isolation — same query, different namespace/top_k ===")
    # Same query, different params → different keys → no cross-contamination
    k1 = cache_key("what is ai", "namespace_a", 5)
    k2 = cache_key("what is ai", "namespace_b", 5)
    k3 = cache_key("what is ai", "namespace_a", 10)

    assert k1 != k2, "Different namespaces must produce different keys"
    assert k1 != k3, "Different top_k must produce different keys"
    assert k2 != k3

    print(f"  namespace_a, top_k=5  → {k1}")
    print(f"  namespace_b, top_k=5  → {k2}")
    print(f"  namespace_a, top_k=10 → {k3}")
    print(f"  All keys distinct ✓")


# --- Flush test keys from Redis after run ---
async def flush_test_keys():
    r = await get_redis()
    keys = await r.keys("cache:*")
    if keys:
        await r.delete(*keys)
    print(f"\n[cleanup] Flushed {len(keys)} test keys from Redis")


async def main():
    print("Lab 6.1: Cache-Aside Pattern")
    print(f"TTL configured: {CACHE_TTL_SECONDS}s")

    # Verify Redis is reachable before running tests
    r = await get_redis()
    await r.ping()
    print("Redis connection: ok\n")

    miss_latencies, hit_latencies = await test_miss_then_hit()
    
    # Generate the chart
    plot_cache_latency_chart(miss_latencies, hit_latencies)
    
    await test_normalization()
    await test_whitespace()
    await test_hit_rate()
    await test_key_isolation()
    await flush_test_keys()

    await close_redis()
    print("\nLab 6.1 complete.")


if __name__ == "__main__":
    asyncio.run(main())
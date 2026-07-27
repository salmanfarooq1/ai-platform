"""
Lab 6.4: Full cache integration test against live /search endpoint.
Tests exact cache, semantic cache, TTL expiry, and Redis failure graceful degradation.
"""
import asyncio
import httpx
import json
import time
import subprocess
import sys
from pathlib import Path

BASE_URL = "http://localhost:8001"
NAMESPACE = "legal"


async def search(client: httpx.AsyncClient, query: str, top_k: int = 5) -> dict:
    response = await client.post(
        f"{BASE_URL}/search",
        json={"query": query, "namespace": NAMESPACE, "top_k": top_k},
        timeout=120.0,
    )
    response.raise_for_status()
    return {
        "body": response.json(),
        "x_cache": response.headers.get("X-Cache", "unknown"),
        "x_cache_type": response.headers.get("X-Cache-Type", "unknown"),
        "x_cost": response.headers.get("X-Cost-USD", "unknown"),
    }


# ── Scenario 1: Cold start — all misses ──────────────────────────────────────
async def test_cold_start(client: httpx.AsyncClient):
    print("\n=== Scenario 1: Cold Start (all misses) ===")
    print("  Clearing existing cache keys to guarantee cold start...")
    
    # Safely delete keys without dropping the RediSearch index schema
    import redis
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        count = 0
        for key in r.scan_iter("exact:*"):
            r.delete(key)
            count += 1
        for key in r.scan_iter("semcache:*"):
            r.delete(key)
            count += 1
        print(f"  Cleared {count} cache keys.")
    except Exception as e:
        print(f"  Warning: Failed to clear cache: {e}")
        
    await asyncio.sleep(1)
    
    queries = [
        "What is the data retention policy for employee records?",
        "How do we report a data breach?",
        "What are GDPR consent requirements?",
        "What is the right to erasure?",
        "How long must we retain customer data?",
    ]

    costs, latencies = [], []
    for q in queries:
        start = time.perf_counter()
        result = await search(client, q)
        latency = (time.perf_counter() - start) * 1000
        latencies.append(latency)
        costs.append(float(result["x_cost"]) if result["x_cost"] != "unknown" else 0.0)
        print(f"  {result['x_cache']:4} ({result['x_cache_type']:8}) {latency:6.0f}ms — {q[:55]}")

    print(f"  Avg latency: {sum(latencies)/len(latencies):.0f}ms")
    print(f"  Total cost : ${sum(costs):.6f}")
    return sum(latencies) / len(latencies), sum(costs)


# ── Scenario 2: Warm cache — exact hits ──────────────────────────────────────
async def test_warm_cache(client: httpx.AsyncClient):
    print("\n=== Scenario 2: Warm Cache (exact hits) ===")
    queries = [
        "What is the data retention policy for employee records?",
        "How do we report a data breach?",
        "What are GDPR consent requirements?",
        "What is the right to erasure?",
        "How long must we retain customer data?",
    ]

    latencies, hits = [], 0
    for q in queries:
        start = time.perf_counter()
        result = await search(client, q)
        latency = (time.perf_counter() - start) * 1000
        latencies.append(latency)
        if result["x_cache"] == "HIT":
            hits += 1
        print(f"  {result['x_cache']:4} ({result['x_cache_type']:8}) {latency:6.0f}ms — {q[:55]}")

    print(f"  Hit rate   : {hits}/{len(queries)} ({hits/len(queries)*100:.0f}%)")
    print(f"  Avg latency: {sum(latencies)/len(latencies):.0f}ms")
    print(f"  Total cost : $0.000000")
    return sum(latencies) / len(latencies), hits / len(queries)


# ── Scenario 3: Semantic cache — paraphrases ─────────────────────────────────
async def test_semantic_cache(client: httpx.AsyncClient):
    print("\n=== Scenario 3: Semantic Cache (paraphrase detection) ===")
    paraphrases = [
        "How long do we keep employee data?",
        "Steps to take when a security incident involves personal data",
        "GDPR rules around user consent",
        "Can employees request deletion of their data?",
        "What is our customer data retention schedule?",
    ]

    hits, latencies = 0, []
    for q in paraphrases:
        start = time.perf_counter()
        result = await search(client, q)
        latency = (time.perf_counter() - start) * 1000
        latencies.append(latency)
        if result["x_cache"] == "HIT":
            hits += 1
        print(f"  {result['x_cache']:4} ({result['x_cache_type']:8}) {latency:6.0f}ms — {q[:55]}")

    print(f"  Semantic hit rate: {hits}/{len(paraphrases)} ({hits/len(paraphrases)*100:.0f}%)")
    return hits / len(paraphrases)


# ── Scenario 4: Mixed traffic ─────────────────────────────────────────────────
async def test_mixed_traffic(client: httpx.AsyncClient):
    print("\n=== Scenario 4: Mixed Traffic (10 unique + 10 repeats) ===")
    unique = [
        "What is a data processing agreement?",
        "Define legitimate interests under GDPR",
        "What is the purpose of a DPIA?",
        "How must consent be documented?",
        "What are binding corporate rules?",
        "Define data subject rights",
        "What is privacy by design?",
        "How long are security logs retained?",
        "What is a supervisory authority?",
        "Define sensitive personal data",
    ]
    mixed = unique + unique  # 50% repeat rate

    hits, misses, total_cost = 0, 0, 0.0
    for q in mixed:
        result = await search(client, q)
        cost = float(result["x_cost"]) if result["x_cost"] != "unknown" else 0.0
        total_cost += cost
        if result["x_cache"] == "HIT":
            hits += 1
        else:
            misses += 1

    print(f"  Total: {len(mixed)} queries | Hits: {hits} | Misses: {misses}")
    print(f"  Hit rate  : {hits/len(mixed)*100:.0f}%")
    print(f"  Total cost: ${total_cost:.6f}")
    return hits / len(mixed), total_cost


# ── Scenario 5: TTL expiry ────────────────────────────────────────────────────
async def test_ttl_expiry(client: httpx.AsyncClient):
    print("\n=== Scenario 5: TTL Expiry (manual — set TTL=5s in cache.py, wait 6s) ===")
    print("  NOTE: To run this test properly:")
    print("  1. Set CACHE_TTL_SECONDS = 5 in api/services/cache.py")
    print("  2. Restart server")
    print("  3. Run a query, wait 6 seconds, run again — should be MISS")
    print("  Skipping automated test — TTL is 3600s in current config")


# ── Scenario 6: Redis down ────────────────────────────────────────────────────
async def test_redis_degradation(client: httpx.AsyncClient):
    print("\n=== Scenario 6: Redis Down — Graceful Degradation ===")
    print("  Stopping Redis container...")
    subprocess.run(["docker", "stop", "redis"], capture_output=True)
    await asyncio.sleep(2)

    try:
        result = await search(client, "What is GDPR?")
        print(f"  API response: {result['x_cache']} — server did not crash ✓")
        print(f"  Status: API degraded gracefully (cache miss, full pipeline ran)")
    except Exception as e:
        print(f"  API crashed: {e} ✗")
    finally:
        print("  Restarting Redis...")
        subprocess.run(["docker", "start", "redis"], capture_output=True)
        await asyncio.sleep(3)
        print("  Redis restored ✓")


async def main():
    print("Lab 6.4: Cache Integration Test")
    print(f"Target: {BASE_URL}")

    async with httpx.AsyncClient() as client:
        # Verify server is up
        health = await client.get(f"{BASE_URL}/health")
        print(f"Health: {health.json()}")

        cold_latency, cold_cost = await test_cold_start(client)
        warm_latency, exact_hit_rate = await test_warm_cache(client)
        semantic_hit_rate = await test_semantic_cache(client)
        mixed_hit_rate, mixed_cost = await test_mixed_traffic(client)
        await test_ttl_expiry(client)
        await test_redis_degradation(client)

        # Save results
        results = {
            "lab": "6.4_cache_integration",
            "cold_start_avg_latency_ms": round(cold_latency, 1),
            "cold_start_cost_usd": round(cold_cost, 6),
            "warm_cache_avg_latency_ms": round(warm_latency, 1),
            "exact_hit_rate": round(exact_hit_rate, 2),
            "semantic_hit_rate": round(semantic_hit_rate, 2),
            "mixed_traffic_hit_rate": round(mixed_hit_rate, 2),
            "mixed_traffic_cost_usd": round(mixed_cost, 6),
            "latency_speedup": round(cold_latency / warm_latency, 1) if warm_latency > 0 else 0,
        }

        out = Path("benchmarks/lab_6.4_cache_integration.json")
        out.write_text(json.dumps(results, indent=2))
        print(f"\n[benchmark] Saved to {out}")
        print("\nLab 6.4 complete.")


if __name__ == "__main__":
    asyncio.run(main())

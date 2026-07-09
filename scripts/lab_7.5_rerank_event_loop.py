"""
scripts/lab_7.5_rerank_event_loop.py
=====================================
Lab C.5 — Cross-encoder reranking: event-loop impact measurement.

WHAT THIS MEASURES
------------------
asyncio runs on a single thread. If a CPU-heavy function is called directly
inside a coroutine, it freezes the event loop — every other concurrent request
hangs until the call returns.

This lab proves whether that is happening with our cross-encoder reranker:

  Run A (BLOCKING):  rerank() called directly — no offloading
  Run B (OFFLOADED): rerank() dispatched via run_cpu_bound() to ProcessPoolExecutor

PROOF MECHANISM: HEARTBEAT
--------------------------
A "heartbeat" coroutine runs concurrently and tries to tick every 10ms.
If the event loop is free, ticks arrive on time.
If the event loop is blocked, ticks are delayed or go silent.

The maximum heartbeat gap during inference is the measured event-loop lag.

EXPECTED OUTCOME
----------------
  Run A: heartbeat stalls for the full inference duration (~200–800ms)
  Run B: heartbeat ticks normally; max gap stays near 10ms

RESULT INTERPRETATION
---------------------
  If Run B max gap <= 2x tick_interval: safe to set rerank=True in RetrieverConfig
  If Run B max gap >> tick_interval:    something is still blocking; investigate
"""

import asyncio
import time
from pathlib import Path
import json
import sys

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.services.retriever import rerank, get_cross_encoder
from core.processing.cpu_offload import run_cpu_bound

# ---------------------------------------------------------------------------
# Synthetic candidates — realistic size: 20 chunks of ~300 chars each.
# The cross-encoder runs pairwise (query, chunk) scoring on all of these.
# ---------------------------------------------------------------------------
QUERY = "what is the data minimization principle and how does it apply to extraneous fields"

CANDIDATES = [
    {
        "id": f"chunk_{i}",
        "document_id": f"doc_{i // 5}",
        "content": f"Synthetic compliance chunk {i}: "
                   "Under GDPR Article 5, personal data must be adequate, relevant and limited "
                   "to what is necessary in relation to the purposes for which they are processed. "
                   "Organizations must not collect extraneous fields that serve no documented purpose. "
                   f"This is chunk number {i} of the synthetic test set.",
        "source_filename": f"gdpr_policy_{i // 5}.md",
        "rrf_score": 1.0 / (60 + i + 1),
    }
    for i in range(20)
]

TICK_INTERVAL_S = 0.010   # heartbeat fires every 10ms
TOP_K = 5
RESULTS_PATH = Path("benchmarks/lab_7.5_event_loop_results.json")


# ---------------------------------------------------------------------------
# Heartbeat probe
# ---------------------------------------------------------------------------
async def heartbeat(stop_event: asyncio.Event, gaps: list[float]) -> None:
    """
    Fires every TICK_INTERVAL_S and records the actual gap since the last tick.
    If the event loop is blocked, the gap will be much larger than TICK_INTERVAL_S.
    """
    last = time.perf_counter()
    while not stop_event.is_set():
        await asyncio.sleep(TICK_INTERVAL_S)
        now = time.perf_counter()
        gaps.append(now - last)
        last = now


# ---------------------------------------------------------------------------
# Run A: Direct (blocking) call
# ---------------------------------------------------------------------------
async def run_blocking() -> dict:
    print("\n" + "=" * 60)
    print("RUN A — BLOCKING (rerank called directly on event loop)")
    print("=" * 60)

    gaps: list[float] = []
    stop = asyncio.Event()

    heartbeat_task = asyncio.create_task(heartbeat(stop, gaps))

    t0 = time.perf_counter()
    # This call is SYNCHRONOUS — it will block the event loop for its full duration
    result = rerank(QUERY, [dict(c) for c in CANDIDATES], TOP_K)
    elapsed = time.perf_counter() - t0

    stop.set()
    await heartbeat_task

    max_gap_ms = max(gaps) * 1000 if gaps else 0.0
    mean_gap_ms = (sum(gaps) / len(gaps)) * 1000 if gaps else 0.0
    tick_count = len(gaps)

    print(f"  Inference time     : {elapsed * 1000:.1f} ms")
    print(f"  Heartbeat ticks    : {tick_count}")
    print(f"  Max heartbeat gap  : {max_gap_ms:.1f} ms  ← event-loop stall")
    print(f"  Mean heartbeat gap : {mean_gap_ms:.1f} ms")
    print(f"  Top result score   : {result[0].get('rerank_score', 'N/A'):.4f}")

    return {
        "mode": "blocking",
        "inference_ms": round(elapsed * 1000, 2),
        "heartbeat_ticks": tick_count,
        "max_gap_ms": round(max_gap_ms, 2),
        "mean_gap_ms": round(mean_gap_ms, 2),
    }


# ---------------------------------------------------------------------------
# Run B: Offloaded via run_cpu_bound (non-blocking)
# ---------------------------------------------------------------------------
async def run_offloaded() -> dict:
    print("\n" + "=" * 60)
    print("RUN B — OFFLOADED (rerank via run_cpu_bound)")
    print("=" * 60)

    gaps: list[float] = []
    stop = asyncio.Event()

    heartbeat_task = asyncio.create_task(heartbeat(stop, gaps))

    t0 = time.perf_counter()
    # run_cpu_bound dispatches to ProcessPoolExecutor — event loop stays free
    result = await run_cpu_bound(rerank, QUERY, [dict(c) for c in CANDIDATES], TOP_K)
    elapsed = time.perf_counter() - t0

    stop.set()
    await heartbeat_task

    max_gap_ms = max(gaps) * 1000 if gaps else 0.0
    mean_gap_ms = (sum(gaps) / len(gaps)) * 1000 if gaps else 0.0
    tick_count = len(gaps)

    print(f"  Inference time     : {elapsed * 1000:.1f} ms  (includes IPC overhead)")
    print(f"  Heartbeat ticks    : {tick_count}")
    print(f"  Max heartbeat gap  : {max_gap_ms:.1f} ms  ← event-loop stall")
    print(f"  Mean heartbeat gap : {mean_gap_ms:.1f} ms")
    print(f"  Top result score   : {result[0].get('rerank_score', 'N/A'):.4f}")

    return {
        "mode": "offloaded",
        "inference_ms": round(elapsed * 1000, 2),
        "heartbeat_ticks": tick_count,
        "max_gap_ms": round(max_gap_ms, 2),
        "mean_gap_ms": round(mean_gap_ms, 2),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    print("Lab 7.5 — Cross-encoder event-loop impact measurement")
    print(f"Query      : {QUERY[:60]}...")
    print(f"Candidates : {len(CANDIDATES)} chunks")
    print(f"Tick       : every {TICK_INTERVAL_S * 1000:.0f} ms")

    # ------------------------------------------------------------------
    # Step 0: Warmup — must happen BEFORE any heartbeat measurement.
    #
    # Why: get_cross_encoder() does a disk load (~300-800ms) on first call.
    # Without warmup, Run A's 202,936 ms was almost entirely the HuggingFace
    # download, not inference. The heartbeat never fired because the download
    # consumed the entire window before asyncio.sleep() could tick.
    #
    # We also warm the process pool worker with a dummy 2-candidate call.
    # ProcessPoolExecutor workers have their own memory space — they load the
    # model independently from disk on their first task. Without this, Run B
    # would also silently stall on the worker's cold start.
    # ------------------------------------------------------------------
    print("\n[Warmup] Loading cross-encoder model into main process RAM...")
    get_cross_encoder()  # disk -> RAM for the main process
    print("[Warmup] Pre-warming process pool worker (dummy inference)...")
    await run_cpu_bound(rerank, QUERY, [dict(c) for c in CANDIDATES[:2]], 1)
    print("[Warmup] Done. Both the main process and pool worker have the model in RAM.")
    print("         Starting measurements now — numbers below are pure inference.\n")

    result_a = await run_blocking()
    # Small pause so the process pool worker from run_cpu_bound is not
    # competing with the blocking run's residual CPU usage
    await asyncio.sleep(1.0)
    result_b = await run_offloaded()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # IMPORTANT: 0 heartbeat ticks means the event loop was frozen for the
    # ENTIRE inference duration — no coroutine could be scheduled at all.
    # We report this as a stall equal to inference_ms, not 0ms.
    blocking_stall = (
        result_a["inference_ms"]
        if result_a["heartbeat_ticks"] == 0
        else result_a["max_gap_ms"]
    )
    offloaded_stall = result_b["max_gap_ms"]
    stall_reduction = blocking_stall - offloaded_stall

    print(f"  Blocking stall     : {blocking_stall:.1f} ms  "
          f"({'complete freeze — 0 ticks fired' if result_a['heartbeat_ticks'] == 0 else 'max gap'})")
    print(f"  Offloaded max gap  : {offloaded_stall:.1f} ms  ({result_b['heartbeat_ticks']} ticks fired normally)")
    print(f"  Stall reduction    : {stall_reduction:.1f} ms")

    threshold = TICK_INTERVAL_S * 1000 * 2  # 2× tick = acceptable
    verdict = "✅ SAFE — flip rerank=True" if offloaded_stall <= threshold else "⚠️  STILL BLOCKING — investigate"
    print(f"  Verdict            : {verdict}")

    # Save results
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "lab": "7.5 — Cross-encoder event-loop impact",
        "tick_interval_ms": TICK_INTERVAL_S * 1000,
        "safe_threshold_ms": threshold,
        "results": [result_a, result_b],
        "verdict": verdict,
    }
    RESULTS_PATH.write_text(json.dumps(summary, indent=2))
    print(f"\n  Results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

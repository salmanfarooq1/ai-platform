"""
Lab 4.3 — Hybrid Async + Multiprocessing
==========================================
The production pattern for CPU-heavy pipelines:

    async def process_document(doc):
        content = await fetch(doc)                          # I/O — async, non-blocking
        result  = await loop.run_in_executor(pool, cpu_fn) # CPU — process pool, non-blocking to event loop
        await store(result)                                 # I/O — async, non-blocking

WHY THIS MATTERS:
  If you call a CPU-heavy function directly inside an async coroutine
  (without run_in_executor), it BLOCKS the event loop. No other coroutine
  can run while it's computing. Your entire async concurrency collapses
  to sequential for that duration.

  run_in_executor() offloads the CPU work to a separate process, hands
  control BACK to the event loop immediately, and awaits the result
  asynchronously. The event loop stays free to handle other tasks.

WHAT WE MEASURE:
  - Naive:  CPU work called directly in async → blocks event loop
  - Hybrid: CPU work in process pool via run_in_executor → event loop stays free
  - A "responsiveness probe" coroutine runs concurrently to show whether
    the event loop was blocked or not
"""

import asyncio
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Simulated workloads
# ---------------------------------------------------------------------------

def heavy_cpu_work(_=None) -> int:
    """CPU-bound. Must be a plain function (not async) to run in a process."""
    return sum(i * i for i in range(3_000_000))


async def simulate_io(label: str, duration: float = 0.05) -> str:
    """Simulates a network call or DB query. Non-blocking."""
    await asyncio.sleep(duration)
    return f"{label}_done"


# ---------------------------------------------------------------------------
# Responsiveness probe
# Runs concurrently. If event loop is blocked, this probe will be delayed.
# We measure how long it actually takes vs how long it should take.
# ---------------------------------------------------------------------------

async def responsiveness_probe(expected_interval: float, results: list) -> None:
    """
    Wakes up every `expected_interval` seconds and records actual wake time.
    If the event loop is blocked, actual wake time > expected_interval.
    """
    start = time.perf_counter()
    for i in range(8):
        await asyncio.sleep(expected_interval)
        actual = time.perf_counter() - start
        expected = expected_interval * (i + 1)
        delay = actual - expected
        results.append(round(delay * 1000, 2))  # delay in ms


# ---------------------------------------------------------------------------
# Two versions of the pipeline
# ---------------------------------------------------------------------------

async def process_document_naive(doc_id: int) -> float:
    """
    WRONG way: CPU work called directly in async.
    Blocks the event loop for the duration of heavy_cpu_work().
    """
    await simulate_io(f"fetch_{doc_id}")
    start = time.perf_counter()
    heavy_cpu_work()                        # ← BLOCKS the event loop here
    cpu_time = time.perf_counter() - start
    await simulate_io(f"store_{doc_id}")
    return cpu_time


async def process_document_hybrid(doc_id: int, loop: asyncio.AbstractEventLoop,
                                   pool: ProcessPoolExecutor) -> float:
    """
    RIGHT way: CPU work offloaded to process pool via run_in_executor.
    Event loop is free while CPU work runs in a separate process.
    """
    await simulate_io(f"fetch_{doc_id}")
    start = time.perf_counter()
    await loop.run_in_executor(pool, heavy_cpu_work)   # ← hands control back to event loop
    cpu_time = time.perf_counter() - start
    await simulate_io(f"store_{doc_id}")
    return cpu_time


# ---------------------------------------------------------------------------
# Runners — process N documents concurrently
# ---------------------------------------------------------------------------

async def run_naive(n_docs: int) -> dict:
    probe_delays = []

    start = time.perf_counter()
    probe_task = asyncio.create_task(responsiveness_probe(0.05, probe_delays))
    doc_tasks  = [process_document_naive(i) for i in range(n_docs)]
    await asyncio.gather(*doc_tasks)
    await probe_task
    total = time.perf_counter() - start

    return {
        "mode":              "naive (CPU blocks event loop)",
        "total_seconds":     round(total, 3),
        "probe_delays_ms":   probe_delays,
        "avg_probe_delay_ms": round(sum(probe_delays) / len(probe_delays), 2) if probe_delays else 0,
        "max_probe_delay_ms": round(max(probe_delays), 2) if probe_delays else 0,
    }


async def run_hybrid(n_docs: int) -> dict:
    probe_delays = []
    loop = asyncio.get_event_loop()

    with ProcessPoolExecutor(max_workers=4) as pool:
        start = time.perf_counter()
        probe_task = asyncio.create_task(responsiveness_probe(0.05, probe_delays))
        doc_tasks  = [process_document_hybrid(i, loop, pool) for i in range(n_docs)]
        await asyncio.gather(*doc_tasks)
        await probe_task
        total = time.perf_counter() - start

    return {
        "mode":              "hybrid (CPU in process pool)",
        "total_seconds":     round(total, 3),
        "probe_delays_ms":   probe_delays,
        "avg_probe_delay_ms": round(sum(probe_delays) / len(probe_delays), 2) if probe_delays else 0,
        "max_probe_delay_ms": round(max(probe_delays), 2) if probe_delays else 0,
    }


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def save_chart(naive: dict, hybrid: dict, output_path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("Lab 4.3 — Hybrid Async + Multiprocessing", fontsize=13)

    # --- Left: total pipeline time ---
    modes = ["Naive\n(CPU blocks loop)", "Hybrid\n(CPU in process pool)"]
    times = [naive["total_seconds"], hybrid["total_seconds"]]
    colors = ["#C44E52", "#55A868"]
    bars = ax1.bar(modes, times, color=colors, width=0.45)
    for bar, t in zip(bars, times):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f"{t:.3f}s", ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Total pipeline time (seconds)", fontsize=11)
    ax1.set_title("Pipeline throughput (lower = better)", fontsize=11)
    ax1.grid(axis="y", alpha=0.3)

    # --- Right: event loop responsiveness (probe delays) ---
    ax2.plot(naive["probe_delays_ms"],  marker="o", linewidth=2,
             label=f"Naive  (avg delay: {naive['avg_probe_delay_ms']}ms)", color="#C44E52")
    ax2.plot(hybrid["probe_delays_ms"], marker="s", linewidth=2,
             label=f"Hybrid (avg delay: {hybrid['avg_probe_delay_ms']}ms)", color="#55A868")
    ax2.axhline(0, color="black", linewidth=0.8, linestyle="--", label="Ideal (0ms delay)")
    ax2.set_xlabel("Probe tick", fontsize=11)
    ax2.set_ylabel("Event loop delay (ms) — lower = more responsive", fontsize=10)
    ax2.set_title("Event loop responsiveness\n(probe wakes every 50ms — delays mean loop was blocked)", fontsize=10)
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  Chart saved → {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    N_DOCS = 4

    print("Lab 4.3 — Hybrid Async + Multiprocessing")
    print(f"Processing {N_DOCS} documents concurrently\n")

    print("[1/2] Naive — CPU work blocks event loop...")
    naive_result = asyncio.run(run_naive(N_DOCS))
    print(f"      Total: {naive_result['total_seconds']}s | "
          f"Avg probe delay: {naive_result['avg_probe_delay_ms']}ms | "
          f"Max: {naive_result['max_probe_delay_ms']}ms")

    print("[2/2] Hybrid — CPU work in process pool...")
    hybrid_result = asyncio.run(run_hybrid(N_DOCS))
    print(f"      Total: {hybrid_result['total_seconds']}s | "
          f"Avg probe delay: {hybrid_result['avg_probe_delay_ms']}ms | "
          f"Max: {hybrid_result['max_probe_delay_ms']}ms")

    # Save JSON
    benchmarks_dir = Path("benchmarks")
    benchmarks_dir.mkdir(exist_ok=True)

    output = {
        "lab": "4.3 — Hybrid Async + Multiprocessing",
        "description": (
            "Proves that CPU work inside async coroutines blocks the event loop. "
            "run_in_executor() offloads CPU to a process pool, keeping the event loop responsive. "
            "The probe coroutine measures event loop delay — high delay = loop was blocked."
        ),
        "n_docs": N_DOCS,
        "time_unit": "seconds for pipeline total, milliseconds for probe delays",
        "naive":  naive_result,
        "hybrid": hybrid_result,
        "speedup": round(naive_result["total_seconds"] / hybrid_result["total_seconds"], 3),
        "event_loop_improvement": (
            f"avg delay reduced from {naive_result['avg_probe_delay_ms']}ms "
            f"to {hybrid_result['avg_probe_delay_ms']}ms"
        ),
    }

    json_path = benchmarks_dir / "lab_4.3_benchmarks.json"
    json_path.write_text(json.dumps(output, indent=2))
    print(f"\n  Results saved → {json_path}")

    save_chart(naive_result, hybrid_result, benchmarks_dir / "lab_4.3_hybrid_benchmarks.png")

    print("\n--- INSIGHT ---")
    print(f"  Speedup:              {output['speedup']}x")
    print(f"  Event loop improved:  {output['event_loop_improvement']}")
    print("\n  KEY TAKEAWAY: run_in_executor() is the bridge between async and CPU-bound work.")
    print("  In your pipeline: embedding and chunking go through run_in_executor.")
    print("  fetch_doc() and store_chunks() stay as plain awaits.")
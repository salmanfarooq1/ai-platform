"""
Lab 4.1 — GIL Proof
====================
Proves that the GIL prevents true parallelism for CPU-bound work in threads,
while ProcessPoolExecutor achieves real parallelism by spawning separate
Python interpreters (each with their own GIL).

Senior engineer note: this script is diagnostic, not production code.
Single-purpose: run 3 experiments, save numbers, generate chart. That's it.
"""

import json
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# The workload — CPU-bound, no I/O, no sleep. Pure computation.
# This is what the GIL will throttle in threads.
# ---------------------------------------------------------------------------

def heavy_compute(_=None):
    """
    Dummy arg so it works as a map() target with executors.
    Returns the result so the executor doesn't optimize it away.
    """
    return sum(i * i for i in range(5_000_000))


# ---------------------------------------------------------------------------
# Three runners — this is the experiment
# ---------------------------------------------------------------------------

def run_sequential(n: int) -> float:
    """Run heavy_compute n times, one after another. Baseline."""
    start = time.perf_counter()
    for _ in range(n):
        heavy_compute()
    return time.perf_counter() - start


def run_threads(n: int) -> float:
    """
    Run heavy_compute n times across n threads.
    EXPECTED: roughly same as sequential — GIL means only one thread
    executes Python bytecode at a time. Threads don't help CPU-bound work.
    """
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(heavy_compute, range(n)))  # list() forces completion
    return time.perf_counter() - start


def run_processes(n: int) -> float:
    """
    Run heavy_compute n times across n processes.
    EXPECTED: ~n times faster than sequential — each process has its own
    Python interpreter and its own GIL, so they truly run in parallel.
    """
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n) as pool:
        list(pool.map(heavy_compute, range(n)))
    return time.perf_counter() - start


# ---------------------------------------------------------------------------
# Chart — pure boilerplate, nothing to learn here except that it works
# ---------------------------------------------------------------------------

def save_chart(results: dict, output_path: Path) -> None:
    labels = ["Sequential", "4 Threads\n(GIL throttled)", "4 Processes\n(true parallel)"]
    times  = [results["sequential"], results["threads"], results["processes"]]
    colors = ["#4C72B0", "#DD8452", "#55A868"]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, times, color=colors, width=0.5)

    # Annotate each bar with its value
    for bar, t in zip(bars, times):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.05,
            f"{t:.2f}s",
            ha="center", va="bottom", fontsize=11, fontweight="bold"
        )

    ax.set_ylabel("Wall-clock time (seconds)", fontsize=12)
    ax.set_title("Lab 4.1 — GIL Proof: CPU-bound work with 4 workers", fontsize=13)
    ax.set_ylim(0, max(times) * 1.25)

    # Insight annotation
    speedup = results["sequential"] / results["processes"]
    ax.annotate(
        f"Processes are {speedup:.1f}x faster than sequential\n"
        f"Threads are {results['threads']/results['sequential']:.2f}x vs sequential (GIL!)",
        xy=(0.5, 0.85), xycoords="axes fraction",
        ha="center", fontsize=9, color="#555555",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#f0f0f0", alpha=0.8)
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  Chart saved → {output_path}")


# ---------------------------------------------------------------------------
# Main — orchestrate, save, report
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    N_WORKERS = 4

    # --- Write your expectation before running (senior engineer habit) ---
    # Sequential: ~4s  |  Threads: ~4s (GIL)  |  Processes: ~1s (4 cores)

    print("Lab 4.1 — GIL Proof")
    print(f"Running heavy_compute() {N_WORKERS}x in each mode...\n")

    print(f"[1/3] Sequential ({N_WORKERS} runs)...")
    t_seq = run_sequential(N_WORKERS)
    print(f"      → {t_seq:.3f}s")

    print(f"[2/3] Threads ({N_WORKERS} workers)...")
    t_thr = run_threads(N_WORKERS)
    print(f"      → {t_thr:.3f}s")

    print(f"[3/3] Processes ({N_WORKERS} workers)...")
    t_proc = run_processes(N_WORKERS)
    print(f"      → {t_proc:.3f}s")

    results = {
        "n_workers": N_WORKERS,
        "sequential": f"{round(t_seq, 4)}sec",
        "threads":    f"{round(t_thr, 4)}sec",
        "processes":  f"{round(t_proc, 4)}sec",
        "thread_vs_sequential_ratio":  f"{round(t_thr / t_seq, 3)}x",
        "process_speedup_ratio":       f"{round(t_seq / t_proc, 3)}x",
    }

    # Save JSON
    benchmarks_dir = Path("benchmarks")
    benchmarks_dir.mkdir(exist_ok=True)

    json_path = benchmarks_dir / "lab_4.1_gil_proof_benchmarks.json"
    json_path.write_text(json.dumps(results, indent=2))
    print(f"\n  Results saved → {json_path}")

    # Save chart
    save_chart(results, benchmarks_dir / "lab_4.1_gil_proof.png")

    # --- The insight summary (what you should be able to say out loud) ---
    print("\n--- INSIGHT ---")
    print(f"  Threads vs Sequential: {results['thread_vs_sequential_ratio']}x  (expected ≈ 1.0 — GIL)")
    print(f"  Process speedup:       {results['process_speedup_ratio']}x  (expected ≈ {N_WORKERS}.0 — true parallel)")
    print("\n  KEY TAKEAWAY: For CPU-bound work, threads don't help.")
    print("  Use ProcessPoolExecutor. For I/O-bound work, use async or threads.")
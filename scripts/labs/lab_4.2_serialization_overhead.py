"""
Lab 4.2 — Serialization Overhead
==================================
Every time multiprocessing sends data to a worker, Python pickles it.
Every time a worker returns a result, Python unpickles it.
This cost is FIXED per task regardless of how fast the CPU work is.

Goal: find the break-even data size where multiprocessing starts paying off.

Expected pattern:
  - Small data (1KB):   processes SLOWER than sequential (pickle overhead dominates)
  - Large data (10MB):  processes FASTER (CPU work dominates over pickle cost)
  - Somewhere in between: the crossover point
"""

import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Data sizes to test
# ---------------------------------------------------------------------------

DATA_SIZES = {
    "1KB":   1 * 1024,
    "100KB": 100 * 1024,
    "10MB":  10 * 1024 * 1024,
    "100MB": 100 * 1024 * 1024,
}

N_WORKERS = 4

# ---------------------------------------------------------------------------
# Workload — must accept data as argument so it crosses the process boundary
# (this is what gets pickled). Do real CPU work on it.
# ---------------------------------------------------------------------------

def cpu_work(data: bytes) -> str:
    """
    Hash the data 50 times. Forces real CPU work proportional to data size.
    Returns the final hex digest so the result also gets unpickled back.

    WHY 50 iterations: one hash is too fast to measure meaningfully for small
    data. 50 gives us enough signal without making the test take forever.
    """
    result = data
    for _ in range(50):
        result = hashlib.sha256(data).digest()
    return result.hex()


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def run_sequential(data: bytes, n: int) -> float:
    start = time.perf_counter()
    for _ in range(n):
        cpu_work(data)
    return time.perf_counter() - start


def run_processes(data: bytes, n: int) -> float:
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n) as pool:
        list(pool.map(cpu_work, [data] * n))  # [data]*n sends same payload to each worker
    return time.perf_counter() - start


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def save_chart(results: list[dict], output_path: Path) -> None:
    labels     = [r["label"] for r in results]
    seq_ms     = [r["sequential_ms"] for r in results]
    proc_ms    = [r["processes_ms"] for r in results]
    ratios     = [r["proc_speedup_ratio"] for r in results]

    x = list(range(len(labels)))
    width = 0.35

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("Lab 4.2 — Serialization Overhead: where does multiprocessing pay off?", fontsize=13)

    # --- Left: grouped bar chart (time in ms) ---
    bars1 = ax1.bar([i - width/2 for i in x], seq_ms,  width, label="Sequential",  color="#4C72B0")
    bars2 = ax1.bar([i + width/2 for i in x], proc_ms, width, label="4 Processes", color="#DD8452")

    for bar in bars1:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f"{bar.get_height():.1f}ms", ha="center", va="bottom", fontsize=8)
    for bar in bars2:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                 f"{bar.get_height():.1f}ms", ha="center", va="bottom", fontsize=8)

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_xlabel("Data size per task", fontsize=11)
    ax1.set_ylabel("Wall-clock time (milliseconds)", fontsize=11)
    ax1.set_title("Execution time (lower = better)", fontsize=11)
    ax1.legend(fontsize=10)
    ax1.grid(axis="y", alpha=0.3)

    # --- Right: speedup ratio bar (>1 = processes win, <1 = sequential wins) ---
    colors = ["#55A868" if r > 1 else "#C44E52" for r in ratios]
    bars3 = ax2.bar(labels, ratios, color=colors, width=0.5)

    # Reference line at 1.0 = break-even
    ax2.axhline(1.0, color="black", linewidth=1.2, linestyle="--", label="Break-even (ratio = 1.0)")

    for bar, r in zip(bars3, ratios):
        verdict = "processes\nwin" if r > 1 else "sequential\nwins"
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f"{r:.3f}x\n({verdict})", ha="center", va="bottom", fontsize=8.5)

    ax2.set_xlabel("Data size per task", fontsize=11)
    ax2.set_ylabel("Speedup ratio  (seq_time ÷ proc_time)", fontsize=11)
    ax2.set_title("Speedup ratio — above dashed line = processes win", fontsize=11)
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"  Chart saved → {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- Expectation before running ---
    # 1KB:   processes slower (pickle overhead > CPU work)
    # 100KB: roughly similar, maybe processes still slow
    # 10MB:  processes faster (CPU work is heavy enough to justify overhead)

    print("Lab 4.2 — Serialization Overhead")
    print(f"Workers: {N_WORKERS} | Iterations per mode: {N_WORKERS}\n")

    results = []

    for label, size_bytes in DATA_SIZES.items():
        data = b"x" * size_bytes  # simple payload of that size
        print(f"[{label}]")

        t_seq  = run_sequential(data, N_WORKERS)
        t_proc = run_processes(data, N_WORKERS)

        ratio = t_seq / t_proc  # >1 means processes won, <1 means sequential won

        print(f"  Sequential: {t_seq:.4f}s")
        print(f"  Processes:  {t_proc:.4f}s  (ratio {ratio:.2f}x)")
        print(f"  Winner: {'PROCESSES' if ratio > 1 else 'SEQUENTIAL'}\n")

        results.append({
            "label":             label,
            "data_size_bytes":   size_bytes,
            "data_size_human":   label,
            "n_workers":         N_WORKERS,
            "sequential_ms":     round(t_seq  * 1000, 3),
            "processes_ms":      round(t_proc * 1000, 3),
            "proc_speedup_ratio": round(ratio, 4),
            "winner":            "processes" if ratio > 1 else "sequential",
            "interpretation":    (
                f"processes are {ratio:.2f}x faster than sequential"
                if ratio > 1
                else f"sequential is {1/ratio:.2f}x faster — pickle overhead dominates"
            ),
        })

    # Save JSON
    benchmarks_dir = Path("benchmarks")
    benchmarks_dir.mkdir(exist_ok=True)

    output = {
        "lab": "4.2 — Serialization Overhead",
        "description": "Measures pickle/unpickle cost of sending data across process boundaries. Finds break-even data size where multiprocessing starts paying off over sequential.",
        "workload": "hashlib.sha256 x50 iterations per task",
        "n_workers": N_WORKERS,
        "time_unit": "milliseconds (ms)",
        "ratio_explanation": "proc_speedup_ratio = sequential_ms / processes_ms. >1.0 means processes win. <1.0 means sequential wins (pickle overhead dominates).",
        "results": results,
    }

    json_path = benchmarks_dir / "lab_4.2_benchmarks.json"
    json_path.write_text(json.dumps(output, indent=2))
    print(f"  Results saved → {json_path}")

    save_chart(results, benchmarks_dir / "lab_4.2_serialization_overhead.png")

    # Break-even summary
    print("\n--- INSIGHT ---")
    for r in results:
        print(f"  {r['label']:6s}: {r['interpretation']}")

    print("\n  KEY TAKEAWAY: multiprocessing has a fixed serialization cost.")
    print("  Small tasks: use async or threads. Large CPU tasks: use processes.")
    print("  offload heavy embedding/chunking, not small DB writes.")
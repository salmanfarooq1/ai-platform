"""
Lab 2.3 Comparison Script
Compares raw concurrency (Lab 2.2) vs semaphore-controlled concurrency (Lab 2.3)
to show the benefits of controlled concurrency at scale.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


def load_benchmarks():
    """Load both lab 2.2 and lab 2.3 benchmark results"""
    
    # Load Lab 2.2 (raw concurrency)
    with open("./benchmarks/lab_2.2_concurrency_trap_benchmarks.json", "r") as f:
        lab_2_2 = json.load(f)
    
    # Load Lab 2.3 (semaphore-controlled)
    with open("./benchmarks/lab_2.3_controlled_concurrency_benchmarks.json", "r") as f:
        lab_2_3 = json.load(f)
    
    return lab_2_2, lab_2_3


def plot_comparison(lab_2_2, lab_2_3):
    """
    Compare Lab 2.2 (raw concurrency) vs Lab 2.3 (semaphore control)
    
    Lab 2.2 format:
    {
        "concurrency": 100,
        "throughput_rps": 24.3,
        "response_time_seconds": 4.11,
        "success_count": 99,
        "success_percentage": 99.0
    }
    
    Lab 2.3 format:
    {
        "Sem Limit": 100,
        "Time": 10.8,
        "Throuput": 92.61,
        "Success_rate": "999/1000 (99.9%)"
    }
    """
    
    # ── Extract Lab 2.2 data ──────────────────────────────────────────────────
    conc_2_2 = [d["concurrency"] for d in lab_2_2]
    throughput_2_2 = [d["throughput_rps"] for d in lab_2_2]
    success_2_2 = [d["success_percentage"] for d in lab_2_2]
    
    # ── Extract Lab 2.3 data ──────────────────────────────────────────────────
    conc_2_3 = [d["Sem Limit"] for d in lab_2_3]
    throughput_2_3 = [d["Throuput"] for d in lab_2_3]
    
    # Parse success rate from "999/1000 (99.9%)" format
    success_2_3 = []
    for d in lab_2_3:
        rate_str = d["Success_rate"]
        percent_part = rate_str.split("(")[1].split("%")[0]
        success_2_3.append(float(percent_part))
    
    # ── Determine common concurrency levels for fair comparison ───────────────
    # We'll only plot points where both labs tested the same concurrency
    common_levels = sorted(set(conc_2_2) & set(conc_2_3))
    
    # Filter data to common levels
    def filter_by_concurrency(conc_list, data_list, target_levels):
        return [data_list[conc_list.index(c)] for c in target_levels if c in conc_list]
    
    throughput_2_2_filtered = filter_by_concurrency(conc_2_2, throughput_2_2, common_levels)
    success_2_2_filtered = filter_by_concurrency(conc_2_2, success_2_2, common_levels)
    throughput_2_3_filtered = filter_by_concurrency(conc_2_3, throughput_2_3, common_levels)
    success_2_3_filtered = filter_by_concurrency(conc_2_3, success_2_3, common_levels)
    
    # ── Style ─────────────────────────────────────────────────────────────────
    plt.rcParams.update({
        "figure.facecolor": "#0f1117",
        "axes.facecolor":   "#0f1117",
        "axes.edgecolor":   "#2a2d3a",
        "axes.labelcolor":  "#c8ccd8",
        "axes.grid":        True,
        "grid.color":       "#1e2130",
        "grid.linewidth":   0.8,
        "xtick.color":      "#7a7f94",
        "ytick.color":      "#7a7f94",
        "text.color":       "#c8ccd8",
        "font.family":      "monospace",
    })
    
    RAW_COLOR = "#ff6b6b"      # Red for raw/uncontrolled
    SEM_COLOR = "#00e5c7"      # Teal for semaphore-controlled
    SUCCESS_COLOR = "#a78bfa"  # Purple for success rate
    
    # ── Figure ────────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.patch.set_facecolor("#0f1117")
    
    # ══════════════════════════════════════════════════════════════════════════
    # LEFT PLOT: Throughput Comparison
    # ══════════════════════════════════════════════════════════════════════════
    
    # Lab 2.2 (Raw concurrency)
    ax1.plot(
        common_levels, throughput_2_2_filtered,
        color=RAW_COLOR, linewidth=2.5, zorder=3,
        marker="o", markersize=7,
        markerfacecolor="#0f1117", markeredgecolor=RAW_COLOR, markeredgewidth=2,
        label="Lab 2.2: Raw Concurrency",
    )
    
    # Lab 2.3 (Semaphore-controlled)
    ax1.plot(
        common_levels, throughput_2_3_filtered,
        color=SEM_COLOR, linewidth=2.5, zorder=3,
        marker="s", markersize=7,
        markerfacecolor="#0f1117", markeredgecolor=SEM_COLOR, markeredgewidth=2,
        label="Lab 2.3: Semaphore Control",
    )
    
    ax1.set_xlabel("Concurrency Level", fontsize=11, labelpad=10, color="#7a7f94")
    ax1.set_ylabel("Throughput  (req / sec)", fontsize=11, labelpad=10, color="#c8ccd8")
    ax1.set_xscale("log")
    ax1.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax1.set_xticks(common_levels)
    ax1.tick_params(axis="x", labelsize=9)
    ax1.legend(loc="upper left", framealpha=0.15, facecolor="#1a1d26", 
               edgecolor="#2a2d3a", fontsize=10, labelcolor="white")
    ax1.set_title("Throughput Comparison", fontsize=12, color="#e0e3ed", pad=15)
    
    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PLOT: Success Rate Comparison
    # ══════════════════════════════════════════════════════════════════════════
    
    # Lab 2.2 (Raw concurrency)
    ax2.plot(
        common_levels, success_2_2_filtered,
        color=RAW_COLOR, linewidth=2.5, linestyle="--", zorder=3,
        marker="o", markersize=7,
        markerfacecolor="#0f1117", markeredgecolor=RAW_COLOR, markeredgewidth=2,
        label="Lab 2.2: Raw Concurrency",
    )
    
    # Lab 2.3 (Semaphore-controlled)
    ax2.plot(
        common_levels, success_2_3_filtered,
        color=SEM_COLOR, linewidth=2.5, linestyle="--", zorder=3,
        marker="s", markersize=7,
        markerfacecolor="#0f1117", markeredgecolor=SEM_COLOR, markeredgewidth=2,
        label="Lab 2.3: Semaphore Control",
    )
    
    ax2.set_xlabel("Concurrency Level", fontsize=11, labelpad=10, color="#7a7f94")
    ax2.set_ylabel("Success Rate  (%)", fontsize=11, labelpad=10, color="#c8ccd8")
    ax2.set_xscale("log")
    ax2.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax2.set_xticks(common_levels)
    ax2.tick_params(axis="x", labelsize=9)
    ax2.set_ylim(0, 110)
    ax2.axhline(y=99, color="#2a2d3a", linewidth=1, linestyle=":", zorder=0, alpha=0.5)
    ax2.legend(loc="lower left", framealpha=0.15, facecolor="#1a1d26",
               edgecolor="#2a2d3a", fontsize=10, labelcolor="white")
    ax2.set_title("Success Rate Comparison", fontsize=12, color="#e0e3ed", pad=15)
    
    # Annotate the cliff in Lab 2.2 (if it exists in common levels)
    cliff_points = [(c, s) for c, s in zip(common_levels, success_2_2_filtered) if s < 99]
    if cliff_points:
        cliff_c, cliff_s = cliff_points[0]  # First drop below 99%
        ax2.annotate(
            f"Raw cliff: {cliff_s:.1f}%",
            xy=(cliff_c, cliff_s),
            xytext=(cliff_c * 0.3, cliff_s - 15),
            textcoords="data",
            fontsize=9, color=RAW_COLOR,
            arrowprops=dict(arrowstyle="->", color=RAW_COLOR, lw=1.5),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#1a1d26", 
                     edgecolor=RAW_COLOR, alpha=0.9),
        )
    
    # ── Overall title & insight ───────────────────────────────────────────────
    # Calculate key insight
    max_stable_2_2 = max([c for c, s in zip(common_levels, success_2_2_filtered) if s >= 99], default=0)
    max_stable_2_3 = max([c for c, s in zip(common_levels, success_2_3_filtered) if s >= 99], default=0)
    
    if max_stable_2_3 > max_stable_2_2:
        improvement = f"Semaphore control maintains stability up to {max_stable_2_3} concurrent requests  ·  Raw concurrency fails at {max_stable_2_2}"
    else:
        improvement = f"Both approaches tested at concurrency levels: {min(common_levels)} - {max(common_levels)}"
    
    fig.text(
        0.5, 0.97,
        "Lab 2.2 vs Lab 2.3 — Impact of Concurrency Control",
        ha="center", va="top", fontsize=14, fontweight="bold", color="#e0e3ed",
    )
    fig.text(
        0.5, 0.92,
        improvement,
        ha="center", va="top", fontsize=9, color="#7a7f94",
    )
    
    plt.tight_layout(rect=[0, 0, 1, 0.90])
    plt.savefig("./benchmarks/Lab_2.3_comparison.png", dpi=160, bbox_inches="tight")
    print("✅ Saved ./benchmarks/Lab_2.3_comparison.png")
    plt.show()


def main():
    print("Loading benchmark data...")
    lab_2_2, lab_2_3 = load_benchmarks()
    
    print(f"Lab 2.2: {len(lab_2_2)} concurrency levels tested")
    print(f"Lab 2.3: {len(lab_2_3)} semaphore limits tested")
    
    print("\nGenerating comparison plot...")
    plot_comparison(lab_2_2, lab_2_3)


if __name__ == "__main__":
    main()
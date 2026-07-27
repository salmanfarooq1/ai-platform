"""
Lab 3.2 vs 3.3 — Simplified Comparison
Shows the 3-act story: naive baseline → best sync → async bulk winner
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np


def load_benchmarks():
    with open("./benchmarks/lab_3.2_psycopg2_benchmarks.json", "r") as f:
        lab_3_2 = json.load(f)
    with open("./benchmarks/lab_3.3_asyncpg_benchmarks.json", "r") as f:
        lab_3_3 = json.load(f)
    return lab_3_2, lab_3_3


def plot_comparison(lab_3_2, lab_3_3):
    a2 = lab_3_2["approaches"]
    a3 = lab_3_3["approaches"]

    # ── 3-act story: baseline → best sync → async bulk ────────────────────────
    methods = [
        "Row-by-Row\n(psycopg2)",
        "execute_batch\n(psycopg2)",
        "COPY\n(asyncpg)",
    ]
    throughputs = [
        a2[0]["throughput_rows_per_s"],   # row-by-row psycopg2  — baseline
        a2[2]["throughput_rows_per_s"],   # execute_batch         — best sync
        a3[1]["throughput_rows_per_s"],   # COPY asyncpg          — winner
    ]
    times = [
        a2[0]["time_s"],
        a2[2]["time_s"],
        a3[1]["time_s"],
    ]

    # ── Palette — light, clean ────────────────────────────────────────────────
    BG        = "#f7f8fa"
    PANEL     = "#ffffff"
    BORDER    = "#dde1e7"
    TEXT_PRI  = "#1a1d23"
    TEXT_SEC  = "#6b7280"
    LABEL_COL = "#374151"

    # Stepped hues: muted red → amber → teal
    C_BASE = "#e07070"
    C_SYNC = "#e8a23a"
    C_WIN  = "#2bad82"
    bar_colors = [C_BASE, C_SYNC, C_WIN]

    plt.rcParams.update({
        "figure.facecolor":  BG,
        "axes.facecolor":    PANEL,
        "axes.edgecolor":    BORDER,
        "axes.labelcolor":   TEXT_SEC,
        "axes.grid":         True,
        "grid.color":        BORDER,
        "grid.linewidth":    0.8,
        "grid.alpha":        1.0,
        "xtick.color":       TEXT_SEC,
        "ytick.color":       LABEL_COL,
        "text.color":        TEXT_PRI,
        "font.family":       "sans-serif",
        "font.size":         11,
    })

    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=BG)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    n          = len(methods)
    y_pos      = np.arange(n)
    bar_height = 0.52
    x_max      = max(throughputs)

    bars = ax.barh(y_pos, throughputs, height=bar_height,
                   color=bar_colors, linewidth=0, zorder=3)

    # Glow shadow on each bar
    for i, color in enumerate(bar_colors):
        ax.barh(y_pos[i], throughputs[i] + x_max * 0.003,
                height=bar_height + 0.07,
                color=color, alpha=0.12, linewidth=0, zorder=2)

    ax.invert_yaxis()

    ax.set_yticks(y_pos)
    ax.set_yticklabels(methods, fontsize=12, color=LABEL_COL, linespacing=1.45)

    # ── Speedup badges inside bars ────────────────────────────────────────────
    baseline = throughputs[0]
    badges      = [None, f"{throughputs[1]/baseline:.1f}× vs baseline", f"{throughputs[2]/baseline:.0f}× vs baseline"]
    badge_colors = [None, C_SYNC, C_WIN]

    for i, (val, badge, bc) in enumerate(zip(throughputs, badges, badge_colors)):
        if badge and val > x_max * 0.12:
            ax.text(val * 0.5, y_pos[i], badge,
                    va="center", ha="center", fontsize=11,
                    color="#ffffff", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.38",
                              facecolor=bc, edgecolor="none", alpha=0.92),
                    zorder=6)

        label_col = C_WIN if i == 2 else TEXT_SEC
        fw = "bold" if i == 2 else "normal"
        ax.text(val + x_max * 0.015, y_pos[i],
                f"{val:,.0f} rows/s  ({times[i]:.2f}s)",
                va="center", ha="left", fontsize=10.5,
                color=label_col, fontweight=fw, zorder=5)

    # ── Axis ─────────────────────────────────────────────────────────────────
    ax.set_xlim(0, x_max * 1.38)
    ax.set_xlabel("Throughput (rows / second)", fontsize=10.5,
                  color=TEXT_SEC, labelpad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(BORDER)
    ax.tick_params(axis="x", colors=TEXT_SEC, labelsize=9.5)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{int(x/1000)}k" if x >= 1000 else f"{int(x)}")
    )
    ax.grid(axis="x", color=BORDER, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    # ── Progression arrows ────────────────────────────────────────────────────
    ax.annotate("",
        xy=(throughputs[1] * 0.5, y_pos[1] - bar_height/2 - 0.04),
        xytext=(throughputs[0] * 0.5, y_pos[0] + bar_height/2 + 0.04),
        arrowprops=dict(arrowstyle="-|>", color=C_SYNC, lw=1.4, mutation_scale=10),
        zorder=7)
    ax.annotate("",
        xy=(throughputs[2] * 0.5, y_pos[2] - bar_height/2 - 0.04),
        xytext=(throughputs[1] * 0.5, y_pos[1] + bar_height/2 + 0.04),
        arrowprops=dict(arrowstyle="-|>", color=C_WIN, lw=1.4, mutation_scale=10),
        zorder=7)

    # ── Header ────────────────────────────────────────────────────────────────
    num_rows = lab_3_2["num_rows"]
    emb_dim  = lab_3_2["embedding_dimensions"]
    final_speedup = throughputs[2] / throughputs[0]

    fig.suptitle(
        f"Database Insert Performance  —  {num_rows:,} rows · {emb_dim}D embeddings",
        fontsize=14, fontweight="bold", color=TEXT_PRI, y=1.02
    )
    ax.set_title(
        f"asyncpg COPY is  {final_speedup:.0f}×  faster than the naive row-by-row baseline",
        fontsize=11, color=C_WIN, pad=14, fontweight="600"
    )

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_handles = [
        mpatches.Patch(facecolor=C_BASE, label="Baseline  (row-by-row, sync)"),
        mpatches.Patch(facecolor=C_SYNC, label="Best sync  (execute_batch, psycopg2)"),
        mpatches.Patch(facecolor=C_WIN,  label="Async bulk  (COPY, asyncpg)"),
    ]
    ax.legend(handles=legend_handles, loc="lower right",
              frameon=True, framealpha=1,
              facecolor=PANEL, edgecolor=BORDER,
              fontsize=9.5, handlelength=1.1,
              labelcolor=LABEL_COL)

    plt.tight_layout()
    out = "./benchmarks/Lab_3.2_vs_3.3_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"✅ Saved {out}")
    plt.show()


def main():
    print("Loading benchmark data...")
    lab_3_2, lab_3_3 = load_benchmarks()
    print("\nGenerating comparison plot...")
    plot_comparison(lab_3_2, lab_3_3)


if __name__ == "__main__":
    main()
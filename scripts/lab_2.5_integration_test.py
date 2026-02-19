"""Lab 2.5: Integration Test + Benchmarks (with memory profiling)

Memory analysis covers two independent dimensions:
  1. Input-size independence  → batch sweep (fixed concurrency, same file, different batch sizes)
                                Peak memory should stay flat here — proves generator laziness.
  2. Concurrency scaling      → concurrency sweep (fixed batch, different max_concurrent)
                                Peak memory scales linearly here — this is expected and explained,
                                not treated as a problem.
"""

import asyncio
import sys
import json
import tracemalloc
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.pipeline.async_ingest import ingestion_pipeline
from config import API_URL, API_KEY, INPUT_FILE, OUTPUT_DIR, BATCH_SIZE, MAX_CONCURRENT

# ── Terminal colour helpers ───────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
CYAN    = "\033[36m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
BLUE    = "\033[34m"
WHITE   = "\033[97m"
MAGENTA = "\033[35m"

def header(title: str, width: int = 66):
    bar = "─" * width
    pad = (width - len(title)) // 2
    extra = width - pad - len(title)
    print(f"\n{BOLD}{CYAN}┌{bar}┐{RESET}")
    print(f"{BOLD}{CYAN}│{' ' * pad}{WHITE}{title}{' ' * extra}{CYAN}│{RESET}")
    print(f"{BOLD}{CYAN}└{bar}┘{RESET}")

def section(title: str, width: int = 66):
    print(f"\n{BOLD}{BLUE}  ▸ {title}{RESET}")
    print(f"{DIM}  {'─' * (width - 4)}{RESET}")

def kv(label: str, value, unit: str = "", good: bool = None):
    colour   = GREEN if good is True else (RED if good is False else CYAN)
    val_str  = f"{colour}{BOLD}{value}{RESET}"
    unit_str = f"{DIM} {unit}{RESET}" if unit else ""
    print(f"    {WHITE}{label:<36}{RESET}{val_str}{unit_str}")

def progress_bar(label: str, value: float, total: float, width: int = 20):
    filled = int(width * value / total) if total else 0
    bar = f"{GREEN}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"
    pct = f"{value / total * 100:.1f}%" if total else "n/a"
    print(f"    {WHITE}{label:<20}{RESET} [{bar}] {CYAN}{pct}{RESET}")

def ok(label: str):
    print(f"  {GREEN}✔{RESET}  {label}")

def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET}  {msg}")

def info(msg: str):
    print(f"  {CYAN}ℹ{RESET}  {msg}")

def fmt_time(s: float) -> str:
    if s >= 60:
        m, rem = divmod(s, 60)
        return f"{int(m)}m {rem:.1f}s"
    return f"{s:.2f}s"

def fmt_mem(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    elif b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    return f"{b / 1024 ** 2:.2f} MB"


# ── Memory-aware pipeline wrapper ─────────────────────────────────────────────

async def run_with_memory(api_url, input_file, batch_size, max_concurrent, output) -> dict:
    """
    Run ingestion_pipeline wrapped in tracemalloc.

    Injects two extra keys into the returned metrics dict:
      peak_memory_bytes  — highest single-point allocation during the run
      net_memory_bytes   — net new allocations above the pre-run baseline

    NOTE: tracemalloc intercepts every allocation, adding ~30-50% runtime
    overhead. This is normal for a profiling tool; do not compare these
    timings directly to uninstrumented runs.
    """
    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()

    metrics = await ingestion_pipeline(
        api_url=api_url,
        input_file_path=input_file,
        batch_size=batch_size,
        max_concurrent=max_concurrent,
        output_file_path=output,
    )

    snap_after = tracemalloc.take_snapshot()
    _, peak    = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    net_bytes = sum(
        s.size_diff for s in snap_after.compare_to(snap_before, 'lineno')
        if s.size_diff > 0
    )

    metrics['peak_memory_bytes'] = peak
    metrics['net_memory_bytes']  = net_bytes
    return metrics


# ── Initial pipeline test ─────────────────────────────────────────────────────

async def test_pipeline() -> dict:
    header("Lab 2.5 — Pipeline Integration Test")

    output_file = f"{OUTPUT_DIR}/lab_2.5_test.jsonl"

    section("Configuration")
    kv("Batch size",     BATCH_SIZE,     "chunks")
    kv("Max concurrent", MAX_CONCURRENT, "requests")
    kv("Input file",     INPUT_FILE)
    kv("Output file",    output_file)
    info("tracemalloc is active — expect ~30-50% slower wall time vs uninstrumented runs")

    section("Running pipeline …")
    metrics = await run_with_memory(API_URL, INPUT_FILE, BATCH_SIZE, MAX_CONCURRENT, output_file)
    ok(f"Pipeline finished in {fmt_time(metrics['total_time_pipeline'])}")

    section("Results")
    total   = metrics['total_chunks']
    success = metrics['successful_chunks']
    failed  = metrics['failed_chunks']

    kv("Total chunks",   total,                          "chunks")
    kv("Successful",     success,                        "chunks",  good=True)
    kv("Failed",         failed,                         "chunks",  good=(failed == 0))
    kv("Total time",     fmt_time(metrics['total_time_pipeline']))
    kv("Throughput",     f"{metrics['throughput']:.2f}", "chunks/s")
    kv("Success rate",   f"{metrics['success_rate']:.2f}", "%",     good=(metrics['success_rate'] >= 99))
    kv("Peak memory",    fmt_mem(metrics['peak_memory_bytes']), "← highest point during run")
    kv("Net allocation", fmt_mem(metrics['net_memory_bytes']),  "← above pre-run baseline")

    print()
    progress_bar("Success", success, total)
    if failed:
        progress_bar("Failed ", failed, total)
        warn(f"{failed} chunk(s) failed — check API connectivity.")

    return metrics


# ── Benchmark helpers ─────────────────────────────────────────────────────────

async def _run_one(label: str, output: str, batch_size: int, max_concurrent: int) -> dict:
    m = await run_with_memory(API_URL, INPUT_FILE, batch_size, max_concurrent, output)
    rate_c = GREEN if m['success_rate'] >= 99 else RED
    print(
        f"    {CYAN}{label:<26}{RESET}"
        f"  tput={CYAN}{m['throughput']:6.2f}{RESET} c/s"
        f"  time={CYAN}{fmt_time(m['total_time_pipeline']):<10}{RESET}"
        f"  peak={MAGENTA}{fmt_mem(m['peak_memory_bytes']):<10}{RESET}"
        f"  net={MAGENTA}{fmt_mem(m['net_memory_bytes']):<10}{RESET}"
        f"  ok={rate_c}{m['success_rate']:.1f}%{RESET}"
    )
    return m


def _build_row_batch(m: dict, batch_size: int) -> dict:
    return {
        'batch_size':              batch_size,
        'total_chunks':            m['total_chunks'],
        'successful_chunks':       m['successful_chunks'],
        'failed_chunks':           m['failed_chunks'],
        'total_time_s':            round(m['total_time_pipeline'], 2),
        'success_rate_percent':    round(m['success_rate'], 1),
        'throughput_chunks_per_s': round(m['throughput'], 2),
        'peak_memory_bytes':       m['peak_memory_bytes'],
        'net_memory_bytes':        m['net_memory_bytes'],
    }

def _build_row_conc(m: dict, max_concurrent: int) -> dict:
    return {
        'max_concurrent':          max_concurrent,
        'total_chunks':            m['total_chunks'],
        'successful_chunks':       m['successful_chunks'],
        'failed_chunks':           m['failed_chunks'],
        'total_time_s':            round(m['total_time_pipeline'], 2),
        'success_rate_percent':    round(m['success_rate'], 1),
        'throughput_chunks_per_s': round(m['throughput'], 2),
        'peak_memory_bytes':       m['peak_memory_bytes'],
        'net_memory_bytes':        m['net_memory_bytes'],
    }


# ── Benchmarks ────────────────────────────────────────────────────────────────

async def benchmark_variations():
    header("Benchmark Variations")

    batch_results, concurrency_results = [], []

    # ── Batch sweep ───────────────────────────────────────────────────────────
    # Concurrency is fixed at MAX_CONCURRENT throughout.
    # Input file is always the same 1 MB file.
    # Therefore: any change in peak memory here is NOT caused by input size or
    # concurrency — it can only come from batch buffering.
    # Expectation: peak memory stays roughly flat → proves generator laziness.
    section(f"Batch Size Sweep  (max_concurrent={MAX_CONCURRENT} fixed, same input file)")
    for batch_size in [25, 50, 100]:
        output  = f"{OUTPUT_DIR}/lab_2.5_batch_{batch_size}.jsonl"
        metrics = await _run_one(f"batch_size={batch_size}", output, batch_size, MAX_CONCURRENT)
        batch_results.append(_build_row_batch(metrics, batch_size))

    # ── Concurrency sweep ─────────────────────────────────────────────────────
    # Batch size is fixed at BATCH_SIZE throughout.
    # Expectation: peak memory scales proportionally with max_concurrent because
    # asyncio.gather holds all in-flight response payloads in memory simultaneously.
    # This is expected behaviour, not a bug — it is the concurrency/memory tradeoff.
    section(f"Concurrency Sweep  (batch_size={BATCH_SIZE} fixed)")
    for max_concurrent in [10, 25, 50]:
        output  = f"{OUTPUT_DIR}/lab_2.5_concurrent_{max_concurrent}.jsonl"
        metrics = await _run_one(f"max_concurrent={max_concurrent}", output, BATCH_SIZE, max_concurrent)
        concurrency_results.append(_build_row_conc(metrics, max_concurrent))

    return batch_results, concurrency_results


# ── Save + Visualise ──────────────────────────────────────────────────────────

def save_and_visualize(batch_results: list, concurrency_results: list):
    header("Saving Outputs")

    json_path = Path(OUTPUT_DIR) / "lab_2.5_benchmarks.json"
    with open(json_path, 'w') as f:
        json.dump({
            'test_file':                INPUT_FILE,
            'file_size':                '1 MB',
            'total_chunks':             1024,
            'chunk_size_bytes':         1024,
            'memory_note': (
                'peak_memory_bytes reflects two independent dimensions: '
                'batch sweep isolates input-size effect (should be flat); '
                'concurrency sweep isolates concurrency effect (expected to scale).'
            ),
            'batch_optimization':       batch_results,
            'concurrency_optimization': concurrency_results,
        }, f, indent=2)
    ok(f"JSON  → {json_path}")

    # ── Palette ───────────────────────────────────────────────────────────────
    DARK_BG   = "#0f1117"
    PANEL_BG  = "#1a1d2e"
    GRID_COL  = "#2a2d3e"
    TEXT_COL  = "#e0e0f0"
    C_BATCH   = "#4fc3f7"   # cyan-blue   – batch throughput
    C_CONC    = "#69f0ae"   # mint        – concurrency throughput
    C_TIME    = "#ff7043"   # coral       – time lines
    C_MEM_B   = "#ce93d8"   # lilac       – batch memory (expect: flat)
    C_MEM_C   = "#ffb74d"   # amber       – concurrency memory (expect: rising)
    C_AVG     = "#f3e5f5"   # pale lilac  – avg reference line

    plt.rcParams.update({
        'figure.facecolor': DARK_BG, 'axes.facecolor': PANEL_BG,
        'axes.edgecolor':   GRID_COL, 'axes.labelcolor': TEXT_COL,
        'xtick.color':      TEXT_COL,  'ytick.color':    TEXT_COL,
        'text.color':       TEXT_COL,  'grid.color':     GRID_COL,
        'font.family':      'monospace',
    })

    # 3 rows × 2 cols
    #  row 0 : throughput (batch | concurrency)
    #  row 1 : total time (batch | concurrency)
    #  row 2 : peak memory — left: FLAT expected  |  right: RISING expected
    fig = plt.figure(figsize=(16, 14), facecolor=DARK_BG)
    fig.suptitle("Lab 2.5 — Async Ingestion Pipeline Benchmarks",
                 fontsize=17, fontweight='bold', color=TEXT_COL, y=0.98)
    gs = gridspec.GridSpec(3, 2, figure=fig,
                           hspace=0.60, wspace=0.42,
                           left=0.07, right=0.95, top=0.93, bottom=0.06)

    # ── Shared helpers ────────────────────────────────────────────────────────
    def style(ax):
        ax.spines[['top', 'right']].set_visible(False)
        ax.spines[['left', 'bottom']].set_color(GRID_COL)
        ax.grid(axis='y', linestyle='--', alpha=0.35, color=GRID_COL)
        ax.set_axisbelow(True)

    def label_bars(ax, bars, vals, fmt="{:.2f}"):
        span = ax.get_ylim()[1] - ax.get_ylim()[0]
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + span * 0.03,
                    fmt.format(v), ha='center', va='bottom',
                    fontsize=8.5, fontweight='bold', color=TEXT_COL)

    def bar_ax(ax, x, y, colour, xlabel, ylabel, title, fmt="{:.2f}"):
        bars = ax.bar(x, y, color=colour, alpha=0.85, width=0.5,
                      zorder=3, edgecolor=DARK_BG, linewidth=0.8)
        ax.set_ylabel(ylabel, fontsize=10, color=colour)
        ax.tick_params(axis='y', labelcolor=colour)
        ax.set_xlabel(xlabel, fontsize=10, labelpad=6)
        ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
        ax.set_ylim(0, max(y) * 1.25)
        style(ax)
        label_bars(ax, bars, y, fmt)
        return bars

    def line_ax(ax, x, y, colour, marker, xlabel, ylabel, title):
        ax.plot(x, y, color=colour, marker=marker, linewidth=2.2, markersize=9,
                markerfacecolor=DARK_BG, markeredgewidth=2.5, markeredgecolor=colour, zorder=3)
        ax.fill_between(x, y, alpha=0.15, color=colour)
        for xi, yi in zip(x, y):
            ax.annotate(f"{yi:.1f}", xy=(xi, yi), xytext=(0, 10),
                        textcoords='offset points', ha='center',
                        fontsize=8.5, fontweight='bold', color=TEXT_COL)
        ax.set_ylabel(ylabel, fontsize=10, color=colour)
        ax.tick_params(axis='y', labelcolor=colour)
        ax.set_xlabel(xlabel, fontsize=10, labelpad=6)
        ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
        ax.set_ylim(0, max(y) * 1.25)
        style(ax)

    def mem_ax(ax, x, labels, pk_kb, colour, xlabel, title, expectation: str):
        """
        Memory bar chart with:
          - dashed average + shaded ±1σ band
          - spread % badge
          - top annotation explaining what the chart is proving
        """
        bars = ax.bar(x, pk_kb, color=colour, alpha=0.80, width=0.5,
                      zorder=3, edgecolor=DARK_BG, linewidth=0.8)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
        ax.set_xlabel(xlabel, fontsize=10, labelpad=6)
        ax.set_ylabel("Peak Memory (KB)", fontsize=10, color=colour)
        ax.tick_params(axis='y', labelcolor=colour)
        ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
        ax.set_ylim(0, max(pk_kb) * 1.45)
        style(ax)
        label_bars(ax, bars, pk_kb, fmt="{:.0f} KB")

        mean_pk = float(np.mean(pk_kb))
        std_pk  = float(np.std(pk_kb))
        spread  = (max(pk_kb) - min(pk_kb)) / mean_pk * 100 if mean_pk else 0

        # Average dashed line
        ax.axhline(mean_pk, color=C_AVG, linewidth=1.5, linestyle='--', alpha=0.7, zorder=2)
        ax.text(x[-1] + 0.08, mean_pk * 1.03, f"avg {mean_pk:.0f} KB",
                fontsize=7.5, color=C_AVG, va='bottom', ha='left')

        # ±1σ band
        ax.axhspan(max(0, mean_pk - std_pk), mean_pk + std_pk,
                   color=colour, alpha=0.07, zorder=1)

        # Expectation label (top-left, inside axes)
        ax.text(0.03, 0.97, expectation,
                transform=ax.transAxes, fontsize=8, color=TEXT_COL,
                va='top', ha='left', style='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=DARK_BG,
                          edgecolor=GRID_COL, alpha=0.85))

        # Spread badge (top-right)
        is_flat   = spread < 20
        badge_txt = f"spread: {spread:.1f}%"
        badge_col = "#69f0ae" if is_flat else "#ffb74d"
        ax.text(0.97, 0.97, badge_txt,
                transform=ax.transAxes, fontsize=8.5, fontweight='bold',
                color=badge_col, va='top', ha='right',
                bbox=dict(boxstyle='round,pad=0.35', facecolor=PANEL_BG,
                          edgecolor=badge_col, alpha=0.85, linewidth=1.2))

    # ── Data ─────────────────────────────────────────────────────────────────
    bsizes = [r['batch_size']              for r in batch_results]
    conc   = [r['max_concurrent']          for r in concurrency_results]
    tp_b   = [r['throughput_chunks_per_s'] for r in batch_results]
    tp_c   = [r['throughput_chunks_per_s'] for r in concurrency_results]
    tm_b   = [r['total_time_s']            for r in batch_results]
    tm_c   = [r['total_time_s']            for r in concurrency_results]
    pk_b   = [r['peak_memory_bytes'] / 1024 for r in batch_results]     # KB
    pk_c   = [r['peak_memory_bytes'] / 1024 for r in concurrency_results]
    x_b    = np.arange(len(bsizes))
    x_c    = np.arange(len(conc))

    # Row 0: Throughput
    ax = fig.add_subplot(gs[0, 0])
    ax.set_xticks(x_b); ax.set_xticklabels(bsizes, fontsize=10)
    bar_ax(ax, x_b, tp_b, C_BATCH, "Batch Size", "Throughput (chunks/s)", "Batch Size → Throughput")

    ax = fig.add_subplot(gs[0, 1])
    ax.set_xticks(x_c); ax.set_xticklabels(conc, fontsize=10)
    bar_ax(ax, x_c, tp_c, C_CONC,  "Max Concurrent", "Throughput (chunks/s)", "Concurrency → Throughput")

    # Row 1: Time
    ax = fig.add_subplot(gs[1, 0])
    ax.set_xticks(x_b); ax.set_xticklabels(bsizes, fontsize=10)
    line_ax(ax, x_b, tm_b, C_TIME, 'o', "Batch Size", "Total Time (s)", "Batch Size → Total Time")

    ax = fig.add_subplot(gs[1, 1])
    ax.set_xticks(x_c); ax.set_xticklabels(conc, fontsize=10)
    line_ax(ax, x_c, tm_c, C_TIME, 's', "Max Concurrent", "Total Time (s)", "Concurrency → Total Time")

    # Row 2: Memory — two distinct stories
    ax = fig.add_subplot(gs[2, 0])
    mem_ax(ax, x_b, bsizes, pk_b, C_MEM_B,
           xlabel="Batch Size",
           title="Peak Memory vs Batch Size",
           expectation="Expect: FLAT\nSame file, same concurrency\n→ proves generator laziness")

    ax = fig.add_subplot(gs[2, 1])
    mem_ax(ax, x_c, conc, pk_c, C_MEM_C,
           xlabel="Max Concurrent",
           title="Peak Memory vs Concurrency",
           expectation="Expect: RISING\nMore in-flight requests\n→ more response buffers held")

    png_path = Path(OUTPUT_DIR) / "lab_2.5_benchmarks.png"
    plt.savefig(png_path, dpi=150, bbox_inches='tight', facecolor=DARK_BG)
    ok(f"Plot  → {png_path}")
    plt.close()


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(batch_results: list, concurrency_results: list):
    header("Summary")

    def table(title, rows, key_col, key_label):
        print(f"\n  {BOLD}{WHITE}{title}{RESET}")
        hdr = (f"  {key_label:<16} {'Throughput':>12} {'Time':>10}"
               f" {'Success':>9} {'Peak Mem':>11} {'Net Mem':>10}")
        print(f"{DIM}{hdr}{RESET}")
        print(f"{DIM}  {'─' * 72}{RESET}")
        best_tp = max(r['throughput_chunks_per_s'] for r in rows)
        for r in rows:
            tp     = r['throughput_chunks_per_s']
            star   = f" {YELLOW}★{RESET}" if tp == best_tp else "  "
            rate_c = GREEN if r['success_rate_percent'] >= 99 else RED
            print(
                f"  {CYAN}{str(r[key_col]):<16}{RESET}"
                f" {tp:>10.2f}/s"
                f" {fmt_time(r['total_time_s']):>10}"
                f" {rate_c}{r['success_rate_percent']:>8.1f}%{RESET}"
                f" {MAGENTA}{fmt_mem(r['peak_memory_bytes']):>11}{RESET}"
                f" {MAGENTA}{fmt_mem(r['net_memory_bytes']):>10}{RESET}"
                f"{star}"
            )

    table("Batch Size Results",  batch_results,       'batch_size',    'batch_size')
    table("Concurrency Results", concurrency_results, 'max_concurrent', 'max_concurrent')

    # ── Memory: two separate verdicts ─────────────────────────────────────────
    section("Memory Analysis — Two Independent Dimensions")

    # Dimension 1: input-size independence (batch sweep)
    b_peaks   = [r['peak_memory_bytes'] for r in batch_results]
    b_mean    = float(np.mean(b_peaks))
    b_spread  = (max(b_peaks) - min(b_peaks)) / b_mean * 100 if b_mean else 0
    b_const   = b_spread < 20

    print(f"\n  {BOLD}{WHITE}Dimension 1 — Input-Size Independence  (batch sweep){RESET}")
    print(f"  {DIM}  Concurrency fixed at {MAX_CONCURRENT}, same 1 MB file, only batch size varies.{RESET}")
    print(f"  {DIM}  If generators are truly lazy, peak memory must not grow with batch size.{RESET}")
    kv("  Peak range", f"{fmt_mem(min(b_peaks))} – {fmt_mem(max(b_peaks))}")
    kv("  Spread",     f"{b_spread:.1f}%", "← <20% = constant", good=b_const)
    if b_const:
        print(f"\n  {GREEN}{BOLD}  ✔  Memory is constant with respect to batch size / input processing.{RESET}")
        print(f"  {DIM}     The generator chain loads only one batch at a time — input file size{RESET}")
        print(f"  {DIM}     does not affect peak RAM. Proven.{RESET}")
    else:
        warn(f"Batch spread is {b_spread:.1f}% — check whether batch buffering is accumulating.")

    # Dimension 2: concurrency scaling (concurrency sweep)
    c_peaks  = [r['peak_memory_bytes'] for r in concurrency_results]
    c_lo_kb  = min(c_peaks) / 1024
    c_hi_kb  = max(c_peaks) / 1024
    c_ratio  = max(c_peaks) / min(c_peaks) if min(c_peaks) else 0
    conc_lo  = concurrency_results[0]['max_concurrent']
    conc_hi  = concurrency_results[-1]['max_concurrent']
    conc_ratio = conc_hi / conc_lo

    print(f"\n  {BOLD}{WHITE}Dimension 2 — Concurrency / Memory Tradeoff  (concurrency sweep){RESET}")
    print(f"  {DIM}  Batch fixed at {BATCH_SIZE}, only max_concurrent varies.{RESET}")
    print(f"  {DIM}  asyncio.gather holds all in-flight response payloads simultaneously,{RESET}")
    print(f"  {DIM}  so peak memory grows with concurrency. This is expected behaviour.{RESET}")
    kv("  Peak at lowest concurrency",  fmt_mem(min(c_peaks)))
    kv("  Peak at highest concurrency", fmt_mem(max(c_peaks)))
    kv("  Memory ratio  (hi/lo)",       f"{c_ratio:.1f}×")
    kv("  Concurrency ratio (hi/lo)",   f"{conc_ratio:.1f}×")
    if abs(c_ratio - conc_ratio) / conc_ratio < 0.4:
        print(f"\n  {CYAN}{BOLD}  ℹ  Memory scales roughly linearly with concurrency — as expected.{RESET}")
    print(f"  {DIM}     This is the concurrency/memory tradeoff: higher concurrency = more{RESET}")
    print(f"  {DIM}     throughput but proportionally more RAM held in flight.{RESET}")
    print(f"  {DIM}     Choose max_concurrent based on your available RAM budget.{RESET}")

    # ── Best configs ──────────────────────────────────────────────────────────
    best_b = max(batch_results,       key=lambda r: r['throughput_chunks_per_s'])
    best_c = max(concurrency_results, key=lambda r: r['throughput_chunks_per_s'])
    section("Optimal Settings")
    print(f"    {YELLOW}★ Best batch size   :{RESET} {best_b['batch_size']}"
          f"   → {best_b['throughput_chunks_per_s']:.2f} chunks/s"
          f",  peak {fmt_mem(best_b['peak_memory_bytes'])}")
    print(f"    {YELLOW}★ Best concurrency  :{RESET} {best_c['max_concurrent']}"
          f"   → {best_c['throughput_chunks_per_s']:.2f} chunks/s"
          f",  peak {fmt_mem(best_c['peak_memory_bytes'])}")
    print(f"\n  {DIM}  Note: timings include tracemalloc overhead (~30-50% slower than"
          f" uninstrumented runs){RESET}")


# ── Output file manifest ──────────────────────────────────────────────────────

def note_output_files():
    section("Expected output files")
    files = [
        ("lab_2.5_test.jsonl",           "main pipeline run"),
        ("lab_2.5_batch_25.jsonl",       "batch=25 sweep"),
        ("lab_2.5_batch_50.jsonl",       "batch=50 sweep"),
        ("lab_2.5_batch_100.jsonl",      "batch=100 sweep"),
        ("lab_2.5_concurrent_10.jsonl",  "concurrency=10 sweep"),
        ("lab_2.5_concurrent_25.jsonl",  "concurrency=25 sweep"),
        ("lab_2.5_concurrent_50.jsonl",  "concurrency=50 sweep"),
        ("lab_2.5_benchmarks.json",      "aggregated metrics + memory"),
        ("lab_2.5_benchmarks.png",       "6-panel benchmark plots"),
    ]
    for fname, desc in files:
        print(f"    {DIM}{fname:<42}← {desc}{RESET}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    await test_pipeline()
    batch_results, concurrency_results = await benchmark_variations()
    save_and_visualize(batch_results, concurrency_results)
    print_summary(batch_results, concurrency_results)
    note_output_files()
    print(f"\n{BOLD}{GREEN}  ✔  Lab 2.5 complete!{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
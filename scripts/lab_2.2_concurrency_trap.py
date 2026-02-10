import aiohttp
import asyncio
import time
import json

# first, create a function to fetch dummy url and return status code
async def fetch_url(session, url):
    '''
    expected:
    session = async with aiohttp.ClientSession(base_url=base_url) as session:
    url = the trailing url, can be changed
    '''
    try:
        async with session.get(url, timeout=10) as response:
            # We must await the read to ensure the data actually arrived
            await response.read() 
            return response.status # return only status_code because it is a dummy url
    except Exception as e:
        # Return error name so the benchmark doesn't crash
        return type(e).__name__ 

# now the main benchmark function which implements different level of concurrency
async def benchmark(n, base_url, url):
    '''
    n = number of concurrent requests
    '''
    #start measuring time crucial for benchmarks
    start_time = time.perf_counter()
    async with aiohttp.ClientSession(base_url=base_url) as session: #open session  
        tasks = [asyncio.create_task(fetch_url(session, url)) for _ in range(n)] #create n number of tasks
        results = await asyncio.gather(*tasks) #await all tasks together
    end_time = time.perf_counter() #measure time when finished
    
    response_time = end_time - start_time # time difference (metric 1)
    
    # NEW CALCULATION: Throughput (metric 2)
    # Requests Per Second = Total Requests / Total Time
    rps = n / response_time 
    
    success_rate = sum(1 for r in results if r == 200) # (metric 3)
    
    return n, rps, response_time, success_rate 

async def main():
    conc_list = [1, 5, 10, 25, 50, 100, 200, 500,1000,2000]
    base_url = "https://httpbin.org"
    url = "/delay/1"
    
    # This dictionary will store our final data for JSON export
    benchmarks_results = []
    
    # Updated printing order: Concurrency, Throughput, Time, Successes
    print(f"{'Concurrency':<12} | {'Throughput':<12} | {'Time':<8} | {'Successes':<12}")
    print("-" * 60)
    
    for n_val in conc_list:
        n, rps, response_time, success_rate = await benchmark(n_val, base_url, url)

        success_percentage = success_rate / n * 100
        
        # Store data in a dictionary for this specific 'n'
        bench_dict = {
            "concurrency": n,
            "throughput_rps": round(rps, 2),
            "response_time_seconds": round(response_time, 2),
            "success_count": success_rate,
            "success_percentage": f'{round(success_percentage, 2)}%'
        }
        benchmarks_results.append(bench_dict)
        
        # Output printing 
        print(f"{n:<12} | {rps:>6.2f} req/s | {response_time:>6.2f}s | {success_rate:>4}/{n:<7} ({success_percentage:>6.2f}%)")


    # SAVE TO JSON
    BENCHMARK_SAVE_PATH = 'benchmarks/lab_2.2_concurrency_trap_benchmarks.json'
    try:
        with open(BENCHMARK_SAVE_PATH, "w") as f:
            json.dump(benchmarks_results, f, indent=4)
        print(f"\n✅ Benchmarks saved successfully to: {BENCHMARK_SAVE_PATH}")
    except FileNotFoundError:
        print(f"\n⚠️ Could not save to {BENCHMARK_SAVE_PATH}. Please check the placeholder path.")
    
    # PLOT THE BENCHMARKS
    plot_benchmarks(benchmarks_results)

# ------------ Matplotlib code to plot the benchmarks ------------

def plot_benchmarks(benchmarks_results):
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    # ── Extract series from benchmarks_results (produced by main()) ──────────
    concurrency  = [d["concurrency"]        for d in benchmarks_results]
    throughput   = [d["throughput_rps"]     for d in benchmarks_results]
    success_rate = [d["success_percentage"] for d in benchmarks_results]

    # ── Derive subtitle dynamically from the actual results ───────────────────
    stable_up_to  = max(
        (d["concurrency"] for d in benchmarks_results if d["success_percentage"] >= 99),
        default=concurrency[0],
    )
    cliff_entries = [d for d in benchmarks_results if d["success_percentage"] < 99]
    cliff_at      = cliff_entries[0]["concurrency"] if cliff_entries else None

    subtitle = (
        f"System stable up to ~{stable_up_to} concurrent requests"
        + (f"  ·  Cliff begins at {cliff_at:,}" if cliff_at else "")
    )

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

    TEAL  = "#00e5c7"
    AMBER = "#f5a623"
    RED   = "#ff4d6d"

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, ax1 = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#0f1117")

    # Throughput line + fill
    ax1.fill_between(concurrency, throughput, alpha=0.12, color=TEAL, zorder=1)
    ax1.plot(
        concurrency, throughput,
        color=TEAL, linewidth=2.5, zorder=3,
        marker="o", markersize=6,
        markerfacecolor="#0f1117", markeredgecolor=TEAL, markeredgewidth=2,
        label="Throughput (RPS)",
    )
    ax1.set_xlabel("Concurrency", fontsize=11, labelpad=10, color="#7a7f94")
    ax1.set_ylabel("Throughput  (req / sec)", fontsize=11, labelpad=10, color=TEAL)
    ax1.tick_params(axis="y", colors=TEAL)
    ax1.set_xscale("log")
    ax1.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax1.set_xticks(concurrency)
    ax1.tick_params(axis="x", labelsize=9)

    # Annotate first, middle, and last throughput points
    for i, (x, y) in enumerate(zip(concurrency, throughput)):
        if i in {0, len(concurrency) // 2, len(concurrency) - 1}:
            ax1.annotate(
                f"{y}", xy=(x, y),
                xytext=(0, 12), textcoords="offset points",
                ha="center", fontsize=8, color=TEAL, alpha=0.9,
            )

    # ── Success rate (secondary axis) ─────────────────────────────────────────
    ax2 = ax1.twinx()

    # Color-code points: teal >= 99%, amber 50-99%, red < 50%
    point_colors = [
        TEAL  if s >= 99
        else AMBER if s >= 50
        else RED
        for s in success_rate
    ]

    ax2.fill_between(concurrency, success_rate, alpha=0.07, color=AMBER, zorder=1)
    ax2.plot(
        concurrency, success_rate,
        color=AMBER, linewidth=2, linestyle="--", zorder=2,
        label="Success Rate (%)",
    )
    ax2.scatter(concurrency, success_rate, c=point_colors, s=60, zorder=4, linewidths=0)
    ax2.set_ylabel("Success Rate  (%)", fontsize=11, labelpad=10, color=AMBER)
    ax2.tick_params(axis="y", colors=AMBER)
    ax2.set_ylim(0, 110)
    ax2.axhline(y=99, color="#2a2d3a", linewidth=1, linestyle=":", zorder=0)

    # Annotate first drop below 99% and first drop below 50% dynamically
    annotated = set()
    for d in benchmarks_results:
        c, s = d["concurrency"], d["success_percentage"]
        for thresh, color in [(99, AMBER), (50, RED)]:
            if s < thresh and thresh not in annotated:
                annotated.add(thresh)
                ax2.annotate(
                    f"{s:.1f}%\n(c={c:,})",
                    xy=(c, s),
                    xytext=(c * 0.45, s - 20),
                    textcoords="data",
                    fontsize=8, color=color,
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.2),
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a1d26", edgecolor=color, alpha=0.85),
                )

    # ── Legend ────────────────────────────────────────────────────────────────
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2, labels1 + labels2,
        loc="upper left", framealpha=0.15,
        facecolor="#1a1d26", edgecolor="#2a2d3a",
        fontsize=9, labelcolor="white",
    )

    # ── Title & dynamic subtitle ──────────────────────────────────────────────
    fig.text(
        0.5, 0.97,
        "Load Benchmark — Throughput & Success Rate vs Concurrency",
        ha="center", va="top", fontsize=13, fontweight="bold", color="#e0e3ed",
    )
    fig.text(0.5, 0.91, subtitle, ha="center", va="top", fontsize=9, color="#7a7f94")

    plt.tight_layout(rect=[0, 0, 1, 0.90])
    plt.savefig("benchmark_plot.png", dpi=160, bbox_inches="tight")
    print("Saved benchmark_plot.png")
    plt.show()

if __name__ == "__main__":
    asyncio.run(main())
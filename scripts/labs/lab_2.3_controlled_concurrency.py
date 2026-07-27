import asyncio
import aiohttp
import time
import json
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

async def fetch_url_sem(sem, session, url):
    '''
    expected:
    session = async with aiohttp.ClientSession(base_url=base_url) as session:
    url = the trailing url, can be changed
    '''
    async with sem:
        try:
            async with session.get(url, timeout = 10) as response:
                result = await response.json() # await so we can implement asyncio
                return response.status # return only status_code because it is a dummy url, we do not need anything in the response
        except Exception as e:
            return type(e).__name__

async def benchmark_sem(url, base_url, sem_list, n_req = 1000):

    results_data = []
    print(f"{'Sem Limit':<10} | {'Time':<8} | {'Throughput':<15} | {'Success Rate':<12}")
    print("-" * 60)

    async with aiohttp.ClientSession(base_url=base_url) as session: #open session
        for sem_val in sem_list: # loop for each value in semaphores list
            sem = asyncio.Semaphore(sem_val) #create the semaphore obj for each value to benchmark
            start_time = time.perf_counter() #start timer
            tasks = [asyncio.create_task(fetch_url_sem(sem,session, url)) for _ in range(n_req)] #create n number of tasks
            results =  await asyncio.gather(*tasks) #await all tasks together
            end_time = time.perf_counter() # end time
            duration = end_time - start_time
            successes = sum(1 for r in results if r==200) # measure succeeded requests
            success_rate = (successes/n_req) * 100 # measure success percent
            throughput = n_req /duration #calc throuput
            
            results_data.append({
                'Sem Limit': sem_val, 
                'Time': round(duration, 2),
                'Throuput': round(throughput, 2),
                'Success_rate': f'{successes}/{n_req} ({round(success_rate, 2)}%' 
            })
            print(f"{sem_val:<10} | {duration:>6.2f}s | {throughput:>6.2f} req/s   | {successes}/{n_req} ({round(success_rate, 2)}%)")
        return results_data

def plot_benchmarks_results(results):

    # ── Extract series from results (produced by benchmark_sem()) ────────────
    sem_limits   = [d["Sem Limit"] for d in results]
    times        = [d["Time"] for d in results]  # Already a float
    throughput   = [d["Throuput"] for d in results]  # Already a float
    
    # Parse success rate from "999/1000 (99.9%)" format
    success_rate = []
    for d in results:
        # Extract percentage from string like "999/1000 (99.9%)"
        rate_str = d["Success_rate"]
        # Find the part inside parentheses and remove the % sign
        percent_part = rate_str.split("(")[1].split("%")[0]
        success_rate.append(float(percent_part))

    # ── Derive subtitle dynamically from the actual results ───────────────────
    best_throughput_idx = throughput.index(max(throughput))
    best_sem = sem_limits[best_throughput_idx]
    best_rps = throughput[best_throughput_idx]
    
    subtitle = f"Peak throughput: {best_rps:.1f} req/s at semaphore={best_sem}"

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

    TEAL   = "#00e5c7"
    PURPLE = "#a78bfa"
    AMBER  = "#f5a623"

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, ax1 = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#0f1117")

    # Throughput line + fill
    ax1.fill_between(sem_limits, throughput, alpha=0.12, color=TEAL, zorder=1)
    ax1.plot(
        sem_limits, throughput,
        color=TEAL, linewidth=2.5, zorder=3,
        marker="o", markersize=6,
        markerfacecolor="#0f1117", markeredgecolor=TEAL, markeredgewidth=2,
        label="Throughput (RPS)",
    )
    ax1.set_xlabel("Semaphore Limit", fontsize=11, labelpad=10, color="#7a7f94")
    ax1.set_ylabel("Throughput  (req / sec)", fontsize=11, labelpad=10, color=TEAL)
    ax1.tick_params(axis="y", colors=TEAL)
    ax1.set_xscale("log")
    ax1.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax1.set_xticks(sem_limits)
    ax1.tick_params(axis="x", labelsize=9)

    # Annotate peak throughput
    ax1.annotate(
        f"Peak: {best_rps:.1f}",
        xy=(best_sem, best_rps),
        xytext=(0, 15), textcoords="offset points",
        ha="center", fontsize=9, color=TEAL, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#1a1d26", edgecolor=TEAL, alpha=0.9),
    )

    # ── Response time (secondary axis) ────────────────────────────────────────
    ax2 = ax1.twinx()

    ax2.fill_between(sem_limits, times, alpha=0.07, color=PURPLE, zorder=1)
    ax2.plot(
        sem_limits, times,
        color=PURPLE, linewidth=2, linestyle="--", zorder=2,
        marker="s", markersize=5,
        markerfacecolor="#0f1117", markeredgecolor=PURPLE, markeredgewidth=2,
        label="Response Time (sec)",
    )
    ax2.set_ylabel("Response Time  (seconds)", fontsize=11, labelpad=10, color=PURPLE)
    ax2.tick_params(axis="y", colors=PURPLE)

    # Annotate min and max response times
    min_time_idx = times.index(min(times))
    max_time_idx = times.index(max(times))
    
    ax2.annotate(
        f"Fastest: {times[min_time_idx]:.1f}s",
        xy=(sem_limits[min_time_idx], times[min_time_idx]),
        xytext=(0, -20), textcoords="offset points",
        ha="center", fontsize=8, color=PURPLE, alpha=0.9,
    )
    ax2.annotate(
        f"Slowest: {times[max_time_idx]:.1f}s",
        xy=(sem_limits[max_time_idx], times[max_time_idx]),
        xytext=(0, 12), textcoords="offset points",
        ha="center", fontsize=8, color=PURPLE, alpha=0.9,
    )

    # ── Success rate indicator (as text box) ──────────────────────────────────
    avg_success = sum(success_rate) / len(success_rate)
    min_success = min(success_rate)
    
    if min_success >= 99:
        status_color = TEAL
        status_text = f"All runs stable ({min_success:.1f}% min)"
    elif min_success >= 95:
        status_color = AMBER
        status_text = f"Some degradation ({min_success:.1f}% min)"
    else:
        status_color = "#ff4d6d"
        status_text = f"Instability detected ({min_success:.1f}% min)"

    fig.text(
        0.98, 0.02,
        status_text,
        ha="right", va="bottom", fontsize=9, color=status_color,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#1a1d26", edgecolor=status_color, alpha=0.8),
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

    # ── Title & subtitle ──────────────────────────────────────────────────────
    fig.text(
        0.5, 0.97,
        "Semaphore Benchmark — Throughput & Response Time vs Concurrency Limit",
        ha="center", va="top", fontsize=13, fontweight="bold", color="#e0e3ed",
    )
    fig.text(0.5, 0.91, subtitle, ha="center", va="top", fontsize=9, color="#7a7f94")

    plt.tight_layout(rect=[0, 0, 1, 0.90])
    plt.savefig("semaphore_benchmark_plot.png", dpi=160, bbox_inches="tight")
    print("Saved semaphore_benchmark_plot.png")
    plt.show()


async def main():
    sem_list = [10, 25, 50, 100, 200, 500]
    base_url = "https://httpbin.org"
    url = "/delay/0.5"
    results = await benchmark_sem(url, base_url, sem_list, n_req = 1000)

    with open("./benchmarks/lab_2.3_controlled_concurrency_benchmarks.json", "w") as f:
        json.dump(results, f, indent=4)
    plot_benchmarks_results(results)

if __name__ == "__main__":
    asyncio.run(main())
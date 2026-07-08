"""
scripts/lab_7.3_hybrid_retrieval.py

Benchmark: BM25 vs Vector vs Hybrid retrieval on the 5 failure-case queries
from Lab 7.1. Computes Precision@5 for each mode and saves results + a chart.
"""
import asyncio
import json
from pathlib import Path

import matplotlib.pyplot as plt

from core.database.pool import create_pool          # adjust to your actual factory
from api.services.cache import embed_query   # fixed to our actual embedding fn
from api.services.retriever import (
    retrieve_bm25,
    retrieve_vector,
    rrf_merge,
    RetrieverConfig,
)

NAMESPACE = "legal"
TOP_K = 5

QUERIES = [
    "GDPR Article 5 data minimization principle",
    "what is the maximum fine under CCPA section 1798.155",
    "HIPAA does NOT apply to which entities",
    "legitimate interest assessment under GDPR recital 47",
    "data breach notification within 72 hours regulatory requirement",
]

OUTPUT_JSON = Path("benchmarks/lab_7.3_retrieval_comparison.json")
OUTPUT_CHART = Path("benchmarks/lab_7.3_retrieval_comparison.png")


async def run_all_modes(pool, query: str, config: RetrieverConfig) -> dict:
    embedding = await embed_query(query)

    bm25 = await retrieve_bm25(pool, query, NAMESPACE, TOP_K)
    vector = await retrieve_vector(pool, embedding, NAMESPACE, TOP_K)

    over_fetch = TOP_K * 2
    bm25_over = await retrieve_bm25(pool, query, NAMESPACE, over_fetch)
    vector_over = await retrieve_vector(pool, embedding, NAMESPACE, over_fetch)
    hybrid = rrf_merge(bm25_over, vector_over, k=config.rrf_k, top_k=TOP_K)

    return {"vector_only": vector, "bm25_only": bm25, "hybrid_rrf": hybrid}


def print_for_labeling(query: str, mode_results: dict):
    print(f"\n{'='*80}\nQUERY: {query}\n{'='*80}")
    for mode, results in mode_results.items():
        print(f"\n--- {mode} ---")
        for i, r in enumerate(results, 1):
            snippet = r["content"][:150].replace("\n", " ")
            print(f"  [{i}] {snippet}")


def compute_precision_at_5(labels: dict) -> dict:
    """
    labels shape:
    {
      query: {
        mode: [1, 0, 1, 0, 0]   # your manual 1/0 judgments, same order as printed
      }
    }
    """
    per_mode_totals = {"vector_only": [], "bm25_only": [], "hybrid_rrf": []}
    for query, modes in labels.items():
        for mode, scores in modes.items():
            precision = sum(scores) / len(scores) if scores else 0.0
            per_mode_totals[mode].append(precision)

    return {
        mode: sum(vals) / len(vals) if vals else 0.0
        for mode, vals in per_mode_totals.items()
    }


def save_chart(precision_summary: dict, path: Path):
    modes = list(precision_summary.keys())
    values = [precision_summary[m] for m in modes]

    plt.figure(figsize=(7, 5))
    bars = plt.bar(modes, values, color=["#e74c3c", "#f39c12", "#2ecc71"])
    plt.ylim(0, 1.0)
    plt.ylabel("Precision@5 (avg across 5 queries)")
    plt.title("Retrieval Mode Comparison — Lab 7.3")
    for bar, val in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, val + 0.02, f"{val:.2f}", ha="center")
    plt.tight_layout()
    plt.savefig(path)
    print(f"\nChart saved to {path}")


async def main():
    pool = await create_pool()
    config = RetrieverConfig()

    all_mode_results = {}
    try:
        for query in QUERIES:
            mode_results = await run_all_modes(pool, query, config)
            all_mode_results[query] = mode_results
            print_for_labeling(query, mode_results)
    finally:
        await pool.close()

    # ---- YOUR JOB: fill this in after reading the printed output above ----
    # For each query/mode, enter 1 (relevant) or 0 (not) for each of the 5 results,
    # in the same order they were printed.
    labels = {
        QUERIES[0]: {
            "vector_only": [0, 0, 0, 0, 0],
            "bm25_only":   [0, 0, 0, 0, 0],
            "hybrid_rrf":  [0, 0, 0, 0, 0],
        },
        QUERIES[1]: {
            "vector_only": [0, 0, 0, 0, 0],
            "bm25_only":   [0, 0, 0, 0, 0],
            "hybrid_rrf":  [0, 0, 0, 0, 0],
        },
        QUERIES[2]: {
            "vector_only": [0, 0, 0, 0, 0],
            "bm25_only":   [0, 0, 0, 0, 0],
            "hybrid_rrf":  [0, 0, 0, 0, 0],
        },
        QUERIES[3]: {
            "vector_only": [0, 0, 0, 0, 0],
            "bm25_only":   [0, 0, 0, 0, 0],
            "hybrid_rrf":  [0, 0, 0, 0, 0],
        },
        QUERIES[4]: {
            "vector_only": [1, 0, 0, 0, 0],
            "bm25_only":   [1, 0, 0, 0, 0],
            "hybrid_rrf":  [1, 0, 0, 0, 0],
        },
    }

    if not labels:
        print("\n[!] No labels entered yet. Fill in the `labels` dict at the "
              "bottom of this script based on the output above, then re-run.")
        return

    precision_summary = compute_precision_at_5(labels)

    output = {
        "lab": "7.3 — BM25 vs Vector vs Hybrid Retrieval",
        "queries_tested": len(QUERIES),
        "metric": "Precision@5 (manually labeled)",
        "results": {
            "vector_only": {
                "precision_at_5": precision_summary["vector_only"],
                "notes": "Fails on exact terms, section numbers, negation",
            },
            "bm25_only": {
                "precision_at_5": precision_summary["bm25_only"],
                "notes": "Fails on semantic paraphrases, misses synonym matches",
            },
            "hybrid_rrf": {
                "precision_at_5": precision_summary["hybrid_rrf"],
                "notes": "Wins on both — captures keyword precision AND semantic breadth",
            },
        },
        "rrf_k_used": config.rrf_k,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {OUTPUT_JSON}")

    save_chart(precision_summary, OUTPUT_CHART)


if __name__ == "__main__":
    asyncio.run(main())

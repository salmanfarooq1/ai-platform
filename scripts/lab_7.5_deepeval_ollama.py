"""
scripts/lab_7.5_deepeval_ollama.py
======================================
Local RAG Evaluation using DeepEval + Ollama.

Runs all judge evaluations locally against the 'qwen2.5:latest' model inside
the docker compose container. This eliminates Groq API rate limits and daily
token cap blockages entirely.
"""

import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

# DeepEval uses asyncio internally, setting telemetry opt out avoids event loop conflicts
import os
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

sys.path.insert(0, str(Path(__file__).parent.parent))

from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
)
from deepeval.test_case import LLMTestCase

from core.database.pool import create_pool
from api.services.cache import embed_query
from api.services.retriever import retrieve, RetrieverConfig
from api.services.llm import generate_with_citations
from config import LLM_CONFIG
# Force local generation to bypass Groq rate limit completely in this test script
LLM_CONFIG["model"] = "ollama/qwen2.5"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NAMESPACE  = "legal"  # verified compliance corpus namespace
TOP_K      = 5
OUTPUT_PATH = Path("benchmarks/lab_7.5_deepeval_ollama_baseline.json")

MODES = [
    RetrieverConfig(top_k=TOP_K, mode="hybrid",  rerank=False),
    RetrieverConfig(top_k=TOP_K, mode="hybrid",  rerank=True),
]
MODE_NAMES = ["hybrid_rrf", "hybrid_rrf_reranked"]

# Generation model (same as production Groq model)
GEN_MODEL = LLM_CONFIG["model"]

# Local Ollama Judge configuration
# We query the local container endpoint. 
# From host or WSL, localhost:11434 maps to the container.
OLLAMA_API_BASE = "http://localhost:11434"
OLLAMA_JUDGE_MODEL = "qwen2.5:latest"  # matches the model already pulled in container

# ---------------------------------------------------------------------------
# EVAL DATASET
# 10 compliance-domain questions with manually written ground truth answers.
# ---------------------------------------------------------------------------
EVAL_QUESTIONS = [
    {
        "question": "What rights do individuals have under GDPR regarding their personal data?",
        "ground_truth": "Under GDPR, individuals have the right to access their personal data, the right to rectification of inaccurate data, the right to erasure (right to be forgotten), the right to restrict processing, the right to data portability, and the right to object to processing. They also have rights related to automated decision-making and profiling.",
    },
    {
        "question": "What is the maximum fine for a serious GDPR violation?",
        "ground_truth": "The maximum fine for a serious GDPR violation is 20 million euros or 4% of the company's total global annual turnover of the preceding financial year, whichever is higher.",
    },
    {
        "question": "What constitutes personal data under GDPR?",
        "ground_truth": "Personal data under GDPR is any information relating to an identified or identifiable natural person. This includes names, identification numbers, location data, online identifiers, and factors specific to the physical, physiological, genetic, mental, economic, cultural, or social identity of that person.",
    },
    {
        "question": "What are the lawful bases for processing personal data under GDPR?",
        "ground_truth": "The six lawful bases for processing personal data under GDPR are: consent of the data subject, performance of a contract, compliance with a legal obligation, protection of vital interests, performance of a task carried out in the public interest, and legitimate interests pursued by the controller or a third party.",
    },
    {
        "question": "What is the GDPR requirement for data breach notification?",
        "ground_truth": "Under GDPR, data breaches must be reported to the relevant supervisory authority within 72 hours of becoming aware of the breach. If the breach is likely to result in a high risk to individuals, those individuals must also be notified without undue delay.",
    },
    {
        "question": "What does CCPA require companies to disclose to California consumers?",
        "ground_truth": "CCPA requires companies to disclose to California consumers the categories of personal information collected, the purposes for which it is used, the categories of third parties with whom it is shared, and the consumer's rights including the right to know, delete, and opt-out of the sale of their personal information.",
    },
    {
        "question": "What is the HIPAA minimum necessary standard?",
        "ground_truth": "The HIPAA minimum necessary standard requires covered entities to make reasonable efforts to limit the use, disclosure, and requests for protected health information to the minimum necessary to accomplish the intended purpose.",
    },
    {
        "question": "What are the key principles of data minimisation under GDPR?",
        "ground_truth": "Data minimisation under GDPR requires that personal data collected must be adequate, relevant, and limited to what is necessary in relation to the purposes for which it is processed. Controllers should not collect more data than strictly required.",
    },
    {
        "question": "What is the role of a Data Protection Officer under GDPR?",
        "ground_truth": "A Data Protection Officer under GDPR advises the organisation on data protection obligations, monitors compliance with GDPR, conducts data protection impact assessments, and acts as the point of contact for the supervisory authority and data subjects.",
    },
    {
        "question": "What is privacy by design under GDPR?",
        "ground_truth": "Privacy by design under GDPR requires that data protection principles are integrated into the design of systems, products, and processes from the outset, not added as an afterthought. Controllers must implement appropriate technical and organisational measures to integrate data protection into processing activities.",
    },
]


# ---------------------------------------------------------------------------
# DeepEval custom Ollama LLM adapter
# ---------------------------------------------------------------------------
class OllamaJudge(DeepEvalBaseLLM):
    """
    Wraps the local Ollama API as a DeepEval judge.
    """

    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        super().__init__(model_name)

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str, schema=None) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.0},
            "stream": False
        }
        
        # Ollama supports a native 'format': 'json' parameter to enforce valid JSON outputs
        if schema is not None:
            payload["format"] = "json"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))
                return res["message"]["content"]
        except Exception as e:
            print(f"    [ollama-judge] error generating response: {e}")
            return "{}" if schema is not None else ""

    async def a_generate(self, prompt: str, schema=None) -> str:
        # Delegate to the synchronous generate as Ollama API is handled sequentially 
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name


# ---------------------------------------------------------------------------
# Phase 1: Data collection — retrieve + generate for each mode
# ---------------------------------------------------------------------------
async def collect_for_mode(pool, config: RetrieverConfig, mode_name: str) -> list[dict]:
    print(f"\n  [{mode_name}] Collecting {len(EVAL_QUESTIONS)} answers...")
    records = []

    for i, item in enumerate(EVAL_QUESTIONS):
        question     = item["question"]
        ground_truth = item["ground_truth"]

        embedding = await embed_query(question)
        chunks = await retrieve(
            pool=pool,
            query=question,
            query_embedding=embedding,
            namespace=NAMESPACE,
            config=config,
        )

        if not chunks:
            print(f"    Q{i+1}: WARNING — no chunks (namespace={NAMESPACE!r})")
            records.append({
                "question": question,
                "answer": "",
                "contexts": [],
                "ground_truth": ground_truth,
            })
            continue

        db_chunks = [
            {
                "document_id":    c["document_id"],
                "source_filename": c.get("source_filename") or "unknown",
                "text":           c["content"],
                "score": (
                    c["rrf_score"]    if "rrf_score"    in c else
                    c["vector_score"] if "vector_score" in c else
                    c["bm25_score"]   if "bm25_score"   in c else
                    0.0
                ),
            }
            for c in chunks
        ]

        try:
            # RAG answers are generated using the configured generation LLM (Groq Llama-4-Scout)
            answer_obj, _ = await generate_with_citations(question, db_chunks)
            answer = answer_obj.answer
        except Exception as e:
            print(f"    Q{i+1}: LLM error — {e}")
            answer = ""

        contexts = [c["content"] for c in chunks]
        records.append({
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": ground_truth,
        })
        print(f"    Q{i+1}: ✓  chunks={len(contexts)}  answer={len(answer)}ch")

    return records


# ---------------------------------------------------------------------------
# Phase 2: Score with DeepEval (Local Ollama Judge)
# ---------------------------------------------------------------------------
def score_with_deepeval(
    records: list[dict],
    mode_name: str,
    judge: OllamaJudge,
) -> dict:
    """
    Evaluate collected records using local Ollama Judge.
    """
    print(f"\n  [{mode_name}] Scoring {len(records)} responses via local Ollama...")

    # Instantiate metrics with local judge
    metrics = [
        FaithfulnessMetric(     threshold=0.5, model=judge, include_reason=True),
        AnswerRelevancyMetric(  threshold=0.5, model=judge, include_reason=True),
        ContextualPrecisionMetric(threshold=0.5, model=judge, include_reason=True),
        ContextualRecallMetric(   threshold=0.5, model=judge, include_reason=True),
    ]

    metric_keys = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]

    all_scores = []

    for i, rec in enumerate(records):
        if not rec["answer"] or not rec["contexts"]:
            print(f"    Q{i+1}: skipped (no answer or no contexts)")
            all_scores.append({k: 0.0 for k in metric_keys})
            continue

        test_case = LLMTestCase(
            input=rec["question"],
            actual_output=rec["answer"],
            expected_output=rec["ground_truth"],
            retrieval_context=rec["contexts"],
        )

        try:
            # Measure each metric sequentially
            for m in metrics:
                m.measure(test_case)

            scores = {}
            for metric, key in zip(metrics, metric_keys):
                scores[key] = round(metric.score or 0.0, 4)

            print(
                f"    Q{i+1}: "
                f"faith={scores['faithfulness']:.2f}  "
                f"relev={scores['answer_relevancy']:.2f}  "
                f"prec={scores['context_precision']:.2f}  "
                f"recall={scores['context_recall']:.2f}"
            )
            all_scores.append(scores)

        except Exception as e:
            print(f"    Q{i+1}: DeepEval error — {type(e).__name__}: {str(e)[:120]}")
            all_scores.append({k: 0.0 for k in metric_keys})

        # Note: No sleep required here because we are running against a local Ollama container!

    def mean(key):
        vals = [s[key] for s in all_scores]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {k: mean(k) for k in metric_keys}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("Lab 7.5 — RAG Evaluation (DeepEval + Local Ollama)")
    print(f"Questions  : {len(EVAL_QUESTIONS)}")
    print(f"Namespace  : {NAMESPACE}")
    print(f"Modes      : {', '.join(MODE_NAMES)}")
    print(f"Judge LLM  : {OLLAMA_JUDGE_MODEL} (Local)")
    print(f"Gen LLM    : {GEN_MODEL} (Local)")


    # Build the local judge
    judge = OllamaJudge(model_name=OLLAMA_JUDGE_MODEL, base_url=OLLAMA_API_BASE)

    pool = await create_pool()
    all_records: dict[str, list[dict]] = {}
    all_results: dict[str, dict] = {}

    try:
        print("\n" + "=" * 60)
        print("PHASE 1: Data Collection (retrieval + LLM generation)")
        print("=" * 60)
        for config, name in zip(MODES, MODE_NAMES):
            all_records[name] = await collect_for_mode(pool, config, name)
    finally:
        await pool.close()

    print("\n" + "=" * 60)
    print("PHASE 2: Scoring (DeepEval — Local Qwen2.5-7B)")
    print("=" * 60)
    for name in MODE_NAMES:
        all_results[name] = score_with_deepeval(all_records[name], name, judge)

    # Summary table
    print("\n" + "=" * 68)
    print("FINAL RESULTS")
    print("=" * 68)
    print(f"{'Metric':<22} {'hybrid_rrf':>14} {'hybrid+rerank':>16}")
    print("-" * 68)
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        row = f"{metric:<22}"
        for name in MODE_NAMES:
            val = all_results.get(name, {}).get(metric, "N/A")
            row += f"  {str(val):>14}"
        print(row)

    print(f"\n  Target faithfulness   : >= 0.85")
    print(f"  Target context_recall : >= 0.80")

    # Save benchmark
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "lab":            "7.5 — RAG Evaluation",
        "framework":      "deepeval-ollama",
        "judge_llm":      OLLAMA_JUDGE_MODEL,
        "namespace":      NAMESPACE,
        "top_k":          TOP_K,
        "dataset_size":   len(EVAL_QUESTIONS),
        "corpus":         "enterprise_compliance (GDPR/CCPA/HIPAA)",
        "targets":        {"faithfulness": 0.85, "context_recall": 0.80},
        "results":        all_results,
        "questions":      [q["question"] for q in EVAL_QUESTIONS],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\n  Saved → {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

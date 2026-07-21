"""
scripts/lab_7.5_ragas_eval.py
================================
Lab C.6 — RAG Evaluation using DeepEval.

WHY DEEPEVAL (not custom LLM-as-judge, not ragas)
---------------------------------------------------
Custom LLM-as-judge: llama-4-scout on Groq returned literal '0.0' for context
precision and recall regardless of content. it also involves more complexity than using a purpose built library.

ragas 0.4.3: has two internal metric subsystems (old singleton + new collections)
that do not interoperate. we faced 5 distinct API breakages over multiple sessions.

DeepEval: it has already tested prompts designed to work on smaller models, clean
GroqLLM adapter pattern, no dependency on LangChain/VertexAI/datasets.
Same 4 metrics, same semantic meaning, reliable output.

FOUR METRICS
-------------
  Faithfulness       — Every claim in the answer must be supported by contexts.
                       Low = hallucination.
  Answer Relevancy   — Embedding similarity between question and answer.
                       Low = answer is off-topic.
  Context Precision  — Are the retrieved chunks actually relevant to the question?
                       Low = retriever returned noisy chunks.
  Context Recall     — Does the retrieved context cover the ground truth answer?
                       Low = the right chunk was never retrieved.

ARCHITECTURE
-------------
  Phase 1: Data Collection — retrieve + generate for 3 modes (async, fast).
  Phase 2: Scoring — DeepEval evaluate() per test case (sync, rate-limited).

RATE LIMITING
--------------
  Groq free tier: 30 RPM. DeepEval's evaluate() fires metrics sequentially per
  test case by default. We add an explicit asyncio.sleep between questions to
  ensure we never burst above 24 RPM across all judge calls.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# DeepEval uses asyncio internally, setting telemetry opt out avoids event loop conflicts
import os
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

sys.path.insert(0, str(Path(__file__).parent.parent))

from groq import Groq
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
)
from deepeval.test_case import LLMTestCase
from deepeval import evaluate

from core.database.pool import create_pool
from api.services.cache import embed_query
from api.services.retriever import retrieve, RetrieverConfig
from api.services.llm import generate_with_citations
from config import LLM_CONFIG

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NAMESPACE  = "legal"

TOP_K      = 5
OUTPUT_PATH = Path("benchmarks/lab_7.5_ragas_baseline.json")

MODES = [
    RetrieverConfig(top_k=TOP_K, mode="hybrid",  rerank=False),
    RetrieverConfig(top_k=TOP_K, mode="hybrid",  rerank=True),
]
MODE_NAMES = ["hybrid_rrf", "hybrid_rrf_reranked"]

# Groq model for generation (same as production)
GEN_MODEL = LLM_CONFIG["model"]  # groq/meta-llama/llama-4-scout-17b-16e-instruct

# Judge model is separate from generation to avoid bias and rate limit contention.
# llama-3.3-70b-versatile is DeepEval's recommended Groq judge, 70B reasons well.
# We strip the "groq/" prefix because the Groq SDK takes bare model names.
JUDGE_MODEL_NAME = "openai/gpt-oss-120b"


# Between-question pause to stay below Groq 30 RPM free tier
# DeepEval fires 4 metric judge calls per test case.
# 4 calls × 2.5s = 10s minimum per question → 6 questions/min → well under 30 RPM
INTER_QUESTION_SLEEP = 4.0  # seconds

# ---------------------------------------------------------------------------
# EVAL DATASET
# 10 compliance-domain questions with manually written ground truth answers.
# Ground truth is set by human inspection, NOT auto-labelled from model output.
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
# DeepEval custom Groq LLM adapter
# ---------------------------------------------------------------------------
class GroqJudge(DeepEvalBaseLLM):
    """
    Wraps the Groq SDK as a DeepEval judge.

    Design decisions:
    - Uses the synchronous Groq client because DeepEval calls generate()
      synchronously inside its metric compute logic. Wrapping an async call
      in a sync context from within an already-running event loop causes
      "cannot run nested event loop" errors.
    - a_generate() falls back to generate() which is the same pattern recommended by
      DeepEval docs for non-async providers.
    - temperature=0.0 for deterministic judgments.
    - max_tokens=2048 — DeepEval's internal prompts return structured JSON
      with reasoning chains; 16 tokens (our old limit) was truncating them.
    """

    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self._client = Groq(api_key=api_key)
        super().__init__(model_name)

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str, schema=None) -> str:
        import groq
        import time

        kwargs = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 2048,
        }
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        for attempt in range(5):
            try:
                response = self._client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except groq.RateLimitError as e:
                # Groq 120B model has a tight RPM/TPM limit on free tier.
                # Wait 35s on 429 to let the rate limit window reset.
                wait_time = 35.0
                print(f"    [judge] Rate Limit (429) - waiting {wait_time}s (attempt {attempt+1}/5)...")
                time.sleep(wait_time)
            except Exception as e:
                print(f"    [judge] Unexpected error: {type(e).__name__}: {str(e)[:120]}")
                return "{}" if schema is not None else ""

        print("    [judge] All rate limit retries exhausted - returning empty response")
        return "{}" if schema is not None else ""



    async def a_generate(self, prompt: str, schema=None) -> str:
        # DeepEval calls this from async contexts in some metric paths.
        # We delegate to the sync generate() since Groq's async SDK is
        # a different client class. This is safe, having no event loop nesting
        # because DeepEval uses asyncio.to_thread() internally.
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
# Phase 2: Score with DeepEval
# ---------------------------------------------------------------------------
def score_with_deepeval(
    records: list[dict],
    mode_name: str,
    judge: GroqJudge,
) -> dict:
    """
    Convert collected records to DeepEval LLMTestCase objects and evaluate.

    Each LLMTestCase maps to one (question, answer, contexts, ground_truth) row.
    We evaluate question by question with a sleep between them to respect Groq
    rate limits rather than firing all 10 × 4 = 40 judge calls concurrently.
    """
    print(f"\n  [{mode_name}] Scoring {len(records)} responses via DeepEval...")

    # Instantiate metrics once — reused across all test cases
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
            expected_output=rec["ground_truth"],    # required for Recall & Precision
            retrieval_context=rec["contexts"],
        )

        # Measure metrics directly (avoids evaluate API dependency / nested loop issues)
        try:
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

        # Rate limit guard: 4 judge calls per question, 2.5s minimum gap each
        if i < len(records) - 1:
            time.sleep(INTER_QUESTION_SLEEP)

    def mean(key):
        vals = [s[key] for s in all_scores]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {k: mean(k) for k in metric_keys}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("Lab 7.5 — RAG Evaluation (DeepEval)")
    print(f"Questions  : {len(EVAL_QUESTIONS)}")
    print(f"Namespace  : {NAMESPACE}")
    print(f"Modes      : {', '.join(MODE_NAMES)}")
    print(f"Judge LLM  : {JUDGE_MODEL_NAME}")

    # Build the judge once — shared across all modes
    groq_api_key = LLM_CONFIG.get("groq_key") or os.environ.get("GROQ_API_KEY", "")
    if not groq_api_key:
        raise ValueError(
            "GROQ_API_KEY not found. Set it in .env.local or as an env var."
        )

    judge = GroqJudge(model_name=JUDGE_MODEL_NAME, api_key=groq_api_key)

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
    print("PHASE 2: Scoring (DeepEval — 4 metrics)")
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
        "framework":      "deepeval",
        "version":        "4.0.8",
        "judge_llm":      JUDGE_MODEL_NAME,
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

"""
scripts/lab_7.5_deepeval_v3.py
======================================
Robust RAG Evaluation using DeepEval.

Features:
1. Support for Gemini API (Free or Paid Tier via Google AI Studio) for BOTH generation and evaluation.
2. Multiple Providers: Configure "gemini", "groq", or "ollama" for Generation and Judging independently.
3. Maximum Transparency: Prints exact reasoning, metric details, and scores to the console.
4. State Checkpointing: Saves progress question-by-question so restarts resume where they left off.
"""

import asyncio
import json
import sys
import time
import urllib.request
import urllib.error

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

# ---------------------------------------------------------------------------
# Provider & Model Settings
# ---------------------------------------------------------------------------
# Choose providers: "gemini", "groq", or "ollama"
GENERATION_PROVIDER = "gemini"  # Cloud Gemini (fast)
JUDGE_PROVIDER      = "gemini"  # Cloud Gemini (fast)

# Model Names
GEMINI_GEN_MODEL  = "gemini/gemini-3.5-flash"  # Active stable Flash model for generation
GEMINI_JUDGE_MODEL = "gemini-2.5-pro"          # Reasoning model for judging (avoids self-bias)



GROQ_GEN_MODEL   = "groq/meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_JUDGE_MODEL  = "llama-3.3-70b-specdec"

OLLAMA_GEN_MODEL  = "ollama/qwen2.5"
OLLAMA_JUDGE_MODEL = "qwen2.5:latest"

# ---------------------------------------------------------------------------
# Resolve Configuration
# ---------------------------------------------------------------------------
NAMESPACE  = "legal"  # verified compliance corpus namespace
TOP_K      = 5
OUTPUT_PATH = Path("benchmarks/lab_7.5_deepeval_baseline.json")
PROGRESS_FILE = Path("benchmarks/.eval_progress.json")

# Between-question pause to respect API rate limits (Gemini AI Studio Free is 15 RPM)
INTER_QUESTION_SLEEP = 6.5  


# Set up environment and variables based on providers
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_KEY:
    # Look in LLM_CONFIG or fallback env
    GEMINI_KEY = LLM_CONFIG.get("gemini_key", "") or os.environ.get("GOOGLE_API_KEY", "")

if GEMINI_KEY:
    os.environ["GEMINI_API_KEY"] = GEMINI_KEY
    os.environ["GOOGLE_API_KEY"] = GEMINI_KEY

# Set generation model configuration
if GENERATION_PROVIDER == "gemini":
    LLM_CONFIG["model"] = GEMINI_GEN_MODEL
elif GENERATION_PROVIDER == "groq":
    LLM_CONFIG["model"] = GROQ_GEN_MODEL
else:
    LLM_CONFIG["model"] = OLLAMA_GEN_MODEL

GEN_MODEL = LLM_CONFIG["model"]

# Configure Judge LLM Name
if JUDGE_PROVIDER == "gemini":
    JUDGE_MODEL_NAME = GEMINI_JUDGE_MODEL
elif JUDGE_PROVIDER == "groq":
    JUDGE_MODEL_NAME = GROQ_JUDGE_MODEL
else:
    JUDGE_MODEL_NAME = OLLAMA_JUDGE_MODEL

MODES = [
    RetrieverConfig(top_k=TOP_K, mode="hybrid",  rerank=False),
    RetrieverConfig(top_k=TOP_K, mode="hybrid",  rerank=True),
]
MODE_NAMES = ["hybrid_rrf", "hybrid_rrf_reranked"]

# ---------------------------------------------------------------------------
# EVAL DATASET
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
# DeepEval custom Gemini LLM adapter
# ---------------------------------------------------------------------------
class GeminiJudge(DeepEvalBaseLLM):
    """
    Wraps the Gemini Developer API (Google AI Studio) as a DeepEval judge.
    """
    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self.api_key = api_key
        super().__init__(model_name)

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str, schema=None) -> str:
        # Standard REST endpoint for Google AI Studio
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
        contents = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.0,
            }
        }
        
        if schema is not None:
            contents["generationConfig"]["responseMimeType"] = "application/json"

        req = urllib.request.Request(
            url,
            data=json.dumps(contents).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        for attempt in range(4):

            try:
                with urllib.request.urlopen(req) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    text = res["candidates"][0]["content"]["parts"][0]["text"]
                    return text
            except urllib.error.HTTPError as e:
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    error_body = str(e)
                
                print(f"    [gemini-judge] API HTTP Error {e.code}: {error_body[:200]}...")
                if e.code == 429 or "RESOURCE_EXHAUSTED" in error_body:
                    wait = 45.0
                    print(f"    [gemini-judge] Rate limit (429) hit — cooling down for {wait}s (attempt {attempt+1}/4)...")
                else:
                    wait = 15.0
                time.sleep(wait)
            except Exception as e:
                wait = 15.0
                print(f"    [gemini-judge] Unexpected error: {e} — retrying in {wait}s...")
                time.sleep(wait)

        return "{}" if schema is not None else ""


    async def a_generate(self, prompt: str, schema=None) -> str:
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name

# ---------------------------------------------------------------------------
# DeepEval custom Ollama LLM adapter
# ---------------------------------------------------------------------------
class OllamaJudge(DeepEvalBaseLLM):
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
            print(f"    [ollama-judge] error: {e}")
            return "{}" if schema is not None else ""

    async def a_generate(self, prompt: str, schema=None) -> str:
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name


# ---------------------------------------------------------------------------
# Phase 1: Data collection
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

        # Sleep slightly if calling a cloud API for generation to stay clean on limits
        if GENERATION_PROVIDER == "gemini" and i < len(EVAL_QUESTIONS) - 1:
            time.sleep(1.0)

    return records


# ---------------------------------------------------------------------------
# Phase 2: Scoring (Progress Checkpointed + Transparency Logs)
# ---------------------------------------------------------------------------
def score_with_deepeval(
    records: list[dict],
    mode_name: str,
    judge: DeepEvalBaseLLM,
) -> list[dict]:
    """
    Score RAG answers, resuming from progress file if possible, and printing full reasoning details.
    """
    checkpoint = {}
    if PROGRESS_FILE.exists():
        try:
            checkpoint = json.loads(PROGRESS_FILE.read_text())
        except Exception:
            pass

    print(f"\n  [{mode_name}] Scoring {len(records)} responses via {JUDGE_PROVIDER.upper()} judge...")

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
        checkpoint_key = f"{mode_name}_Q{i+1}"
        
        if checkpoint_key in checkpoint:
            scores = checkpoint[checkpoint_key]
            all_scores.append(scores)
            continue

        if not rec["answer"] or not rec["contexts"]:
            scores = {k: 0.0 for k in metric_keys}
            all_scores.append(scores)
            checkpoint[checkpoint_key] = scores
            PROGRESS_FILE.write_text(json.dumps(checkpoint, indent=2))
            continue

        test_case = LLMTestCase(
            input=rec["question"],
            actual_output=rec["answer"],
            expected_output=rec["ground_truth"],
            retrieval_context=rec["contexts"],
        )

        try:
            scores = {}
            reasons = {}
            for metric, key in zip(metrics, metric_keys):
                metric.measure(test_case)
                scores[key] = round(metric.score or 0.0, 4)
                reasons[key] = metric.reason or "No reason provided."

            print(f"\n    --- Q{i+1} Detailed Metrics ---")
            print(f"    Question : {rec['question']}")
            print(f"    Answer   : {rec['answer'][:120]}...")
            print(f"    * Faithfulness     : {scores['faithfulness']:.2f}")
            print(f"      Reason           : {reasons['faithfulness']}")
            print(f"    * Answer Relevancy : {scores['answer_relevancy']:.2f}")
            print(f"      Reason           : {reasons['answer_relevancy']}")
            print(f"    * Context Precision: {scores['context_precision']:.2f}")
            print(f"      Reason           : {reasons['context_precision']}")
            print(f"    * Context Recall   : {scores['context_recall']:.2f}")
            print(f"      Reason           : {reasons['context_recall']}")
            print("-" * 50)

            all_scores.append(scores)
            checkpoint[checkpoint_key] = scores
            PROGRESS_FILE.write_text(json.dumps(checkpoint, indent=2))

        except Exception as e:
            print(f"    Q{i+1}: scoring failed: {type(e).__name__}: {str(e)[:120]}")
            all_scores.append({k: 0.0 for k in metric_keys})

        # Apply rate limiting gap if using a cloud API judge
        if JUDGE_PROVIDER == "gemini" and i < len(records) - 1:
            time.sleep(INTER_QUESTION_SLEEP)

    return all_scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("Lab 7.5 — RAG Evaluation (DeepEval)")
    print(f"Questions  : {len(EVAL_QUESTIONS)}")
    print(f"Namespace  : {NAMESPACE}")
    print(f"Modes      : {', '.join(MODE_NAMES)}")
    print(f"Judge Provider: {JUDGE_PROVIDER.upper()} ({JUDGE_MODEL_NAME})")
    print(f"Gen LLM    : {GEN_MODEL} ({GENERATION_PROVIDER.upper()})")

    if not GEMINI_KEY and (GENERATION_PROVIDER == "gemini" or JUDGE_PROVIDER == "gemini"):
        raise ValueError(
            "GEMINI_API_KEY not found in environment. Please add it to your environment or .env.local file."
        )

    # Build the configured Judge
    if JUDGE_PROVIDER == "gemini":
        judge = GeminiJudge(model_name=JUDGE_MODEL_NAME, api_key=GEMINI_KEY)
    elif JUDGE_PROVIDER == "groq":
        # Import groq judge dynamically via importlib to avoid import syntax errors on dot-named files
        import importlib
        module = importlib.import_module("scripts.lab_7.5_deepeval")
        judge = module.GroqJudge(model_name=JUDGE_MODEL_NAME, api_key=LLM_CONFIG["groq_key"])
    else:
        judge = OllamaJudge(model_name=JUDGE_MODEL_NAME)

    pool = await create_pool()
    all_records: dict[str, list[dict]] = {}
    all_results: dict[str, list[dict]] = {}

    try:
        print("\n" + "=" * 60)
        print("PHASE 1: Data Collection (retrieval + LLM generation)")
        print("=" * 60)
        for config, name in zip(MODES, MODE_NAMES):
            all_records[name] = await collect_for_mode(pool, config, name)
    finally:
        await pool.close()

    print("\n" + "=" * 60)
    print("PHASE 2: Scoring (DeepEval)")
    print("=" * 60)
    for name in MODE_NAMES:
        all_results[name] = score_with_deepeval(all_records[name], name, judge)

    # Calculate means
    final_results = {}
    for name in MODE_NAMES:
        final_results[name] = {}
        scores_list = all_results[name]
        for key in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
            vals = [s[key] for s in scores_list]
            final_results[name][key] = round(sum(vals) / len(vals), 4) if vals else 0.0

    # Summary table
    print("\n" + "=" * 68)
    print("FINAL RESULTS")
    print("=" * 68)
    print(f"{'Metric':<22} {'hybrid_rrf':>14} {'hybrid+rerank':>16}")
    print("-" * 68)
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        row = f"{metric:<22}"
        for name in MODE_NAMES:
            val = final_results.get(name, {}).get(metric, "N/A")
            row += f"  {str(val):>14}"
        print(row)

    # Delete progress cache upon fully successful run
    if PROGRESS_FILE.exists():
        try:
            PROGRESS_FILE.unlink()
        except Exception:
            pass

    # Save benchmark
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "lab":            "7.5 — RAG Evaluation",
        "judge_llm":      JUDGE_MODEL_NAME,
        "judge_provider": JUDGE_PROVIDER,
        "namespace":      NAMESPACE,
        "top_k":          TOP_K,
        "dataset_size":   len(EVAL_QUESTIONS),
        "corpus":         "enterprise_compliance (GDPR/CCPA/HIPAA)",
        "results":        final_results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\n  Saved → {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

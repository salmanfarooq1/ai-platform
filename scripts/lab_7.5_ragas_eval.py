"""
scripts/lab_7.5_ragas_eval.py
================================
Lab C.6 — RAGAS-style Evaluation of Retrieval Quality.

WHY WE IMPLEMENT METRICS OURSELVES
------------------------------------
ragas 0.4.3 has two internal metric subsystems (old singleton + new collections)
that do not interoperate via evaluate(). Attempts to use ragas 0.4.3 directly
surfaced 5 distinct API breakages over multiple runs. The final crash was an
OOM in the process pool worker during Phase 1 data collection — unrelated to
ragas itself but indicative of running too many heavy processes simultaneously.

Our implementation uses the same underlying approach ragas uses:
  - LLM-as-judge (with explicit prompts) for Faithfulness, Context Precision,
    Context Recall
  - Embedding cosine similarity for Answer Relevancy

The prompts are based on the published ragas metric definitions.

FOUR METRICS
-------------
  Faithfulness       — Every claim in the answer must be supported by contexts.
                       Low = hallucination.
  Answer Relevancy   — Cosine similarity between question and answer embeddings.
                       Low = answer is off-topic.
  Context Precision  — Each retrieved chunk scored for relevance, then averaged.
                       Low = retriever returned noisy chunks.
  Context Recall     — Ground truth derivable from retrieved contexts?
                       Low = the right chunk was never retrieved.

WHY A SCRIPT, NOT THE PIPELINE
--------------------------------
LLM-as-judge multiplies calls: 10 questions × 3 modes × ~5 LLM judge calls
each = ~150 extra LLM calls. Run offline as a benchmark, not on every request.
"""

import asyncio
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import litellm
from core.database.pool import create_pool
from api.services.cache import embed_query
from api.services.retriever import retrieve, RetrieverConfig
from api.services.llm import generate_with_citations
from config import LLM_CONFIG

# ---------------------------------------------------------------------------
# Evaluation dataset — 10 question/ground_truth pairs from the compliance corpus
# ---------------------------------------------------------------------------
EVAL_QUESTIONS = [
    {
        "question": "What is the maximum fine under CCPA Section 1798.155 for intentional violations?",
        "ground_truth": "Under CCPA Section 1798.155, the attorney general can levy fines up to $7,500 per intentional violation.",
    },
    {
        "question": "Under GDPR Article 5, what does the data minimization principle require?",
        "ground_truth": "Personal data must be adequate, relevant, and limited to what is necessary for the purposes for which it is processed.",
    },
    {
        "question": "Which entities are explicitly exempt from HIPAA regulations?",
        "ground_truth": "HIPAA does not apply to life insurers, employers, workers compensation carriers, and most schools and school districts.",
    },
    {
        "question": "Within how many hours must a personal data breach be reported to the supervisory authority under GDPR?",
        "ground_truth": "Under GDPR Article 33, personal data breaches must be reported to the supervisory authority within 72 hours of becoming aware of the breach.",
    },
    {
        "question": "What is the minimum retention period for employee personal data after termination of employment?",
        "ground_truth": "Employee personal data must be retained for a minimum of 6 years following the termination of employment.",
    },
    {
        "question": "Are pre-ticked boxes a valid method of obtaining user consent under GDPR?",
        "ground_truth": "No. Pre-ticked boxes, silence, or inactivity do not constitute valid consent under GDPR. Consent must be freely given, specific, informed, and unambiguous.",
    },
    {
        "question": "What agreement must be in place before engaging a third-party data processor?",
        "ground_truth": "A Data Processing Agreement (DPA) must be in place before engaging any third-party processor.",
    },
    {
        "question": "What are the approved mechanisms for transferring personal data outside the European Economic Area?",
        "ground_truth": "Transfers outside the EEA require an adequacy decision, standard contractual clauses, or binding corporate rules.",
    },
    {
        "question": "How long may application logs containing personal data be retained?",
        "ground_truth": "Application and system logs containing personal data must not be retained for more than 90 days.",
    },
    {
        "question": "What rights does a data subject have to access their personal data under GDPR?",
        "ground_truth": "Data subjects have the right to obtain confirmation of whether their data is processed, access a copy of their personal data, and receive information about the purposes and recipients of processing.",
    },
]

NAMESPACE = "default"   # corpus ingested under "default", not "compliance"
TOP_K = 5
OUTPUT_PATH = Path("benchmarks/lab_7.5_ragas_baseline.json")
JUDGE_MODEL = LLM_CONFIG["model"]

# Evaluate all three retrieval modes
MODES = [
    RetrieverConfig(top_k=TOP_K, mode="vector_only", rerank=False),
    RetrieverConfig(top_k=TOP_K, mode="hybrid",      rerank=False),
    RetrieverConfig(top_k=TOP_K, mode="hybrid",      rerank=True),
]
MODE_NAMES = ["vector_only", "hybrid_rrf", "hybrid_rrf_reranked"]


# ---------------------------------------------------------------------------
# LLM judge — single score call
# ---------------------------------------------------------------------------
async def llm_judge(prompt: str) -> float:
    """
    Sends a scoring prompt to the LLM. Expects a single float 0.0–1.0.
    Returns 0.0 on any error (rather than crashing the eval run).
    """
    try:
        response = await litellm.acompletion(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        # Handle cases like "0.85" or "0.85." or "Score: 0.85"
        for token in raw.replace(",", ".").split():
            try:
                return min(1.0, max(0.0, float(token)))
            except ValueError:
                continue
        return 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Metric 1: Faithfulness
# Proportion of answer claims supported by retrieved contexts.
# Based on ragas faithfulness prompt design.
# ---------------------------------------------------------------------------
async def score_faithfulness(answer: str, contexts: list[str]) -> float:
    # Guard: no answer or no contexts → cannot be faithful
    if not answer.strip() or not contexts:
        return 0.0

    context_block = "\n\n".join(f"[Context {i+1}]: {c}" for i, c in enumerate(contexts))
    prompt = f"""Your task is to judge the faithfulness of an answer against retrieved source contexts.

CONTEXTS:
{context_block}

ANSWER: {answer}

Faithfulness measures whether ALL claims made in the answer can be directly inferred
from the contexts above. A score of 1.0 means every statement in the answer is
supported by the contexts. A score of 0.0 means the answer contains facts not found
in any context (hallucination).

Reply with ONLY a decimal number between 0.0 and 1.0. No words, no explanation."""
    return await llm_judge(prompt)


# ---------------------------------------------------------------------------
# Metric 2: Answer Relevancy
# Cosine similarity between question embedding and answer embedding.
# Based on ragas answer_relevancy implementation.
# ---------------------------------------------------------------------------
async def score_answer_relevancy(question: str, answer: str) -> float:
    if not answer.strip():
        return 0.0
    q_vec, a_vec = await asyncio.gather(embed_query(question), embed_query(answer))
    dot = sum(q * a for q, a in zip(q_vec, a_vec))
    mag_q = math.sqrt(sum(x * x for x in q_vec))
    mag_a = math.sqrt(sum(x * x for x in a_vec))
    if mag_q == 0 or mag_a == 0:
        return 0.0
    return round(max(0.0, min(1.0, dot / (mag_q * mag_a))), 4)


# ---------------------------------------------------------------------------
# Metric 3: Context Precision
# For each retrieved chunk: is it relevant to answering the question?
# Mean score across all chunks. Based on ragas context_precision.
# ---------------------------------------------------------------------------
async def score_context_precision(question: str, contexts: list[str]) -> float:
    if not contexts:
        return 0.0

    async def score_one(ctx: str) -> float:
        prompt = f"""Your task is to judge whether a retrieved context chunk is relevant for answering a question.

QUESTION: {question}

CONTEXT CHUNK:
{ctx}

Score this chunk on a scale of 0.0 to 1.0:
  1.0 = directly useful and necessary for answering the question
  0.5 = partially useful or tangentially related
  0.0 = completely irrelevant to the question

Reply with ONLY a decimal number between 0.0 and 1.0. No words, no explanation."""
        return await llm_judge(prompt)

    scores = await asyncio.gather(*[score_one(c) for c in contexts])
    return round(sum(scores) / len(scores), 4)


# ---------------------------------------------------------------------------
# Metric 4: Context Recall
# Can the ground truth answer be derived from the retrieved contexts?
# Based on ragas context_recall.
# ---------------------------------------------------------------------------
async def score_context_recall(ground_truth: str, contexts: list[str]) -> float:
    if not contexts:
        return 0.0

    context_block = "\n\n".join(f"[Context {i+1}]: {c}" for i, c in enumerate(contexts))
    prompt = f"""Your task is to judge context recall: whether the retrieved contexts contain
sufficient information to derive the ground truth answer.

GROUND TRUTH ANSWER:
{ground_truth}

RETRIEVED CONTEXTS:
{context_block}

Score on a scale of 0.0 to 1.0:
  1.0 = the contexts contain all information needed to produce the ground truth answer
  0.5 = the contexts contain some but not all required information
  0.0 = the contexts contain no information relevant to the ground truth

Reply with ONLY a decimal number between 0.0 and 1.0. No words, no explanation."""
    return await llm_judge(prompt)


# ---------------------------------------------------------------------------
# Score one (question, answer, contexts, ground_truth) tuple
# ---------------------------------------------------------------------------
async def evaluate_one(record: dict) -> dict:
    faithfulness, relevancy, precision, recall = await asyncio.gather(
        score_faithfulness(record["answer"], record["contexts"]),
        score_answer_relevancy(record["question"], record["answer"]),
        score_context_precision(record["question"], record["contexts"]),
        score_context_recall(record["ground_truth"], record["contexts"]),
    )
    return {
        "faithfulness":      round(faithfulness, 4),
        "answer_relevancy":  round(relevancy,    4),
        "context_precision": round(precision,    4),
        "context_recall":    round(recall,       4),
    }


# ---------------------------------------------------------------------------
# Phase 1: Data collection — retrieve + generate, bypassing cache
# ---------------------------------------------------------------------------
async def collect_for_mode(pool, config: RetrieverConfig, mode_name: str) -> list[dict]:
    print(f"\n  [{mode_name}] Collecting {len(EVAL_QUESTIONS)} answers...")
    records = []

    for i, item in enumerate(EVAL_QUESTIONS):
        question    = item["question"]
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
            print(f"    Q{i+1}: WARNING — no chunks (namespace={NAMESPACE})")
            records.append({"question": question, "answer": "", "contexts": [], "ground_truth": ground_truth})
            continue

        db_chunks = [
            {
                "document_id":    c["document_id"],
                "source_filename": c.get("source_filename") or "unknown",
                "text":           c["content"],
                "score":          c.get("rrf_score") or c.get("vector_score") or c.get("bm25_score") or 0.0,
            }
            for c in chunks
        ]

        try:
            answer_obj, _ = await generate_with_citations(question, db_chunks)
            answer = answer_obj.answer
        except Exception as e:
            print(f"    Q{i+1}: LLM error — {e}")
            answer = ""

        contexts = [c["content"] for c in chunks]  # full retrieved pool, not just LLM citations
        records.append({"question": question, "answer": answer, "contexts": contexts, "ground_truth": ground_truth})
        print(f"    Q{i+1}: ✓  chunks={len(contexts)}  answer={len(answer)}ch")

    return records


# ---------------------------------------------------------------------------
# Phase 2: Score collected dataset
# ---------------------------------------------------------------------------
async def score_dataset(records: list[dict], mode_name: str) -> dict:
    print(f"\n  [{mode_name}] Scoring {len(records)} responses...")
    all_scores = []

    for i, record in enumerate(records):
        scores = await evaluate_one(record)
        all_scores.append(scores)
        print(
            f"    Q{i+1}: "
            f"faith={scores['faithfulness']:.2f}  "
            f"relev={scores['answer_relevancy']:.2f}  "
            f"prec={scores['context_precision']:.2f}  "
            f"recall={scores['context_recall']:.2f}"
        )

    def mean(key):
        vals = [s[key] for s in all_scores]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {k: mean(k) for k in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("Lab 7.5 — RAGAS-style Evaluation")
    print(f"Questions  : {len(EVAL_QUESTIONS)}")
    print(f"Namespace  : {NAMESPACE}")
    print(f"Modes      : {', '.join(MODE_NAMES)}")
    print(f"Judge LLM  : {JUDGE_MODEL}")

    pool = await create_pool()
    all_records = {}
    all_results = {}

    try:
        print("\n" + "=" * 60)
        print("PHASE 1: Data Collection (retrieval + LLM generation)")
        print("=" * 60)
        for config, name in zip(MODES, MODE_NAMES):
            all_records[name] = await collect_for_mode(pool, config, name)
    finally:
        await pool.close()

    print("\n" + "=" * 60)
    print("PHASE 2: Scoring (LLM-as-judge, 4 metrics)")
    print("=" * 60)
    for name in MODE_NAMES:
        all_results[name] = await score_dataset(all_records[name], name)

    # Summary table
    print("\n" + "=" * 68)
    print("FINAL RESULTS")
    print("=" * 68)
    print(f"{'Metric':<22} {'vector_only':>14} {'hybrid_rrf':>12} {'hybrid+rerank':>14}")
    print("-" * 68)
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        row = f"{metric:<22}"
        for name in MODE_NAMES:
            val = all_results.get(name, {}).get(metric, "N/A")
            row += f"  {str(val):>12}"
        print(row)

    print(f"\n  Target faithfulness   : >= 0.85")
    print(f"  Target context_recall : >= 0.80")

    # Save benchmark
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "lab":               "7.5 — RAGAS-style Evaluation",
        "implementation":    "custom LLM-as-judge (litellm + embed_query)",
        "ragas_library":     False,
        "ragas_note":        "ragas 0.4.3 has fragmented API (old singletons vs new collections) that do not interoperate. Switched to equivalent custom implementation.",
        "judge_llm":         JUDGE_MODEL,
        "namespace":         NAMESPACE,
        "top_k":             TOP_K,
        "dataset_size":      len(EVAL_QUESTIONS),
        "corpus":            "enterprise_compliance (GDPR/CCPA/HIPAA)",
        "targets":           {"faithfulness": 0.85, "context_recall": 0.80},
        "results":           all_results,
        "questions":         [q["question"] for q in EVAL_QUESTIONS],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\n  Saved → {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

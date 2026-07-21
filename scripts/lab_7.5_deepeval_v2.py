"""
scripts/lab_7.5_deepeval.py
================================
Lab C.6 — RAG Evaluation using DeepEval.  (v4 — stop guessing, measure instead)

WHAT CHANGED IN v4 (evidence-based fix — previous run failed on Q1/attempt 1
of mode 1, immediately, even with v3's async_mode=False + inter-mode
cooldown in place)
-----------------------------------------------------------------------
The v3 fixes addressed real problems (internal metric concurrency, no gap
between modes), but the new failure signature — 429 on the very FIRST
judge call of the very FIRST question — means the budget was already gone
BEFORE Phase 2 started. Neither async_mode nor an inter-MODE cooldown can
explain or fix that, because Phase 1 (generation) runs entirely before
either of those ever gets a chance to matter.

Rather than add a fourth guessed sleep value, this pass replaces guessing
with measurement:
1. RATE-LIMIT HEADERS ARE NOW LOGGED, on both successful and failed judge
   calls. Groq returns real x-ratelimit-remaining-tokens / -requests and
   retry-after values on every response — we were never reading them,
   only reacting to the 429 itself with a flat 35s guess. Now the actual
   remaining budget is visible after every call.
2. RETRY-AFTER IS NOW HONORED: when Groq's 429 response includes a
   retry-after (or x-ratelimit-reset-tokens) value, we sleep for THAT
   real duration instead of a flat 35s. Falls back to 35s only if the
   response provides nothing usable.
3. GENERATION-VS-JUDGE MODEL CHECK: at startup, the script now explicitly
   compares LLM_CONFIG['model'] (generation) against JUDGE_MODEL_NAME. If
   they're the same, Phase 1's ~20 generation calls and Phase 2's judge
   calls are provably competing for one budget — printed as a warning,
   not left as a silent assumption.
4. COOLDOWN ADDED BETWEEN PHASE 1 AND PHASE 2: this gap never existed
   before — Phase 2 always started the instant Phase 1's loop finished.
   Given the new failure signature, this is the most direct candidate
   fix, and it's now paired with real header logging so the NEXT run's
   log will show whether the budget was actually near-zero at the
   Phase 1/2 boundary, confirming or ruling this out with evidence
   rather than another round of trial and error.

WHY DEEPEVAL (not custom LLM-as-judge, not ragas)
---------------------------------------------------
Custom LLM-as-judge: llama-4-scout on Groq returned literal '0.0' for context
precision and recall regardless of content. It also involves more complexity
than using a purpose-built library.

ragas 0.4.3: has two internal metric subsystems (old singleton + new
collections) that do not interoperate. We hit 5 distinct API breakages.

DeepEval: tested prompts designed to work on smaller models, clean Groq
adapter pattern, no LangChain/VertexAI/datasets dependency. Same 4 metrics,
same semantic meaning, reliable output.

WHAT CHANGED IN v3 (concurrency + cooldown fix — see run log from previous
session, where hybrid_rrf completed cleanly but hybrid_rrf_reranked hit
repeated 429s starting from Q2)
-----------------------------------------------------------------------
1. ASYNC_MODE=FALSE ON ALL 4 METRICS (the real fix): DeepEval's metrics
   default to async_mode=True, which means each metric.measure() call
   internally fires MULTIPLE concurrent judge calls under the hood (e.g.
   FaithfulnessMetric = extract claims -> extract truths -> compare, each
   a separate LLM call). INTER_METRIC_SLEEP only spaces calls BETWEEN
   metrics — it has zero visibility into concurrent sub-calls happening
   INSIDE a single metric. That internal concurrency, not call cadence,
   is what was blowing through the judge model's TPM budget. Confirmed
   against DeepEval's own docs, not inferred from behavior alone.
   Tradeoff: forcing sequential internal execution increases per-call
   latency. Given the priority is correct/complete scores over wall-clock
   time, that tradeoff is accepted here.
2. INTER-MODE COOLDOWN ADDED: previously there was zero gap between
   hybrid_rrf finishing and hybrid_rrf_reranked starting, even though both
   share the same judge model's rate-limit pool. Groq's TPM limit is a
   rolling 60s window, so mode 1's tail-end token usage was still counted
   against the limit when mode 2's (concurrent, pre-fix) calls piled on
   top of it. A flat cooldown between modes now gives that window a
   chance to clear before the next mode starts hammering the same pool.
3. script_version bumped to "v3" in the output JSON so saved benchmark
   files are self-describing about which rate-limit fixes were active.

WHAT CHANGED IN v2 (bugfix pass — see run log from prior session)
-----------------------------------------------------------------------
1. REASON LOGGING: metric.reason is now captured and saved. Previously we
   only read .score, so a suspicious 1.00/0.00 pattern couldn't be checked
   against WHY the judge scored it that way.
2. RATE LIMIT GAP FIXED: the old docstring claimed "4 calls x 2.5s between
   them" but the code only slept BETWEEN questions, not between the 4
   metric calls inside one question. That mismatch is the most likely
   cause of the 429s we saw even with a "guard" in place. Now we actually
   sleep between each of the 4 metric calls.
3. PER-METRIC ERROR ISOLATION: previously one metric raising an exception
   discarded all 4 scores for that question, including ones that had
   already computed correctly. Each metric is now measured independently.
4. REAL vs ERROR vs SKIPPED are now distinguishable, both in the console
   and in the saved JSON. Errored/skipped metrics are excluded from the
   mean instead of silently counted as 0.0 (which was quietly dragging
   averages down and making "did retrieval fail" and "did the judge call
   fail" look identical).
5. GroqJudge no longer swallows unexpected errors into a fake "{}" / ""
   response. It logs and re-raises, so failures surface as a real error
   in the per-metric handling above instead of pretending to be a valid
   (and misleadingly confident) judge output.
6. threshold-based .success is now recorded per metric, not dead config.
7. Per-question detail (scores, success, reasons, errors) is persisted to
   the output JSON, not just the aggregate means.
8. Stale comment (wrong judge model name) fixed. Unused GEN_MODEL constant
   removed; generation model is printed directly from LLM_CONFIG instead.

DELIBERATELY NOT IN THIS PASS
-------------------------------
- Suite 2 (multi-hop cross-domain) / Suite 3 (OOD rejection) restructuring,
  GEval wiring, pass-rate aggregation. Real work, but it needs question
  sets that don't exist yet (data refinement work, tracked separately) —
  not something blocking today's baseline numbers.
- Retry-After-aware backoff (still a flat 35s wait). Cosmetic improvement,
  not correctness-affecting.

FOUR METRICS
-------------
  Faithfulness       — Every claim in the answer must be supported by contexts.
  Answer Relevancy   — Embedding similarity between question and answer.
  Context Precision  — Are the retrieved chunks actually relevant?
  Context Recall     — Does the retrieved context cover the ground truth?

ARCHITECTURE
-------------
  Phase 1: Data Collection — retrieve + generate for 2 modes (async, fast).
  Phase 2: Scoring — DeepEval metrics, one question at a time, rate-limited,
           with a cooldown between modes (v3).
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
from deepeval import evaluate  # noqa: F401  (kept — not currently used, see docstring)

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

# Judge model — separate from the generation model to avoid self-grading bias
# and to keep judge-call rate limiting isolated from generation-call limits.
#
# v3: switched from openai/gpt-oss-120b (8K TPM free tier) to
# llama-3.3-70b-versatile (12K TPM free tier). The actual bottleneck was
# never request cadence (both models: 30 RPM) — it's tokens-per-minute.
# Each judge call carries the question + up to TOP_K retrieved chunks +
# ground_truth in the prompt, plus max_tokens=2048 of output. On 8K TPM
# that's ~3-4 calls before the budget is gone for the minute, no matter
# how well-spaced the requests are. 12K TPM gives real headroom instead.
JUDGE_MODEL_NAME = "llama-3.3-70b-versatile"

# --- Rate limiting -----------------------------------------------------
# Groq free tier is tight on this judge model. DeepEval fires one call per
# metric — 4 metrics per question. We space BOTH within-question calls and
# between-question calls, matching what the old docstring claimed but the
# old code never actually did.
INTER_METRIC_SLEEP   = 2.5   # seconds between each of the 4 metric calls
INTER_QUESTION_SLEEP = 4.0   # seconds between questions

# v3: cooldown between modes. Both modes score against the same judge
# model, which shares one rate-limit pool with a rolling ~60s TPM window.
# Without a gap here, mode 2 starts while mode 1's tail-end token usage is
# still counted against that window — compounding with mode 2's own calls
# and triggering 429s almost immediately (as seen in the previous run).
INTER_MODE_SLEEP = 60.0

METRIC_DEFS = [
    # v3: async_mode=False on every metric. Each metric internally runs
    # multiple sub-steps as separate judge calls (e.g. Faithfulness =
    # extract claims -> extract truths -> compare). With DeepEval's default
    # async_mode=True, those sub-steps fire CONCURRENTLY inside a single
    # metric.measure() call — invisible to INTER_METRIC_SLEEP, which only
    # spaces calls BETWEEN metrics, not sub-calls within one. That internal
    # concurrency was the actual source of the TPM bursts. async_mode=False
    # forces those sub-steps to run sequentially instead. This increases
    # per-call latency but directly caps peak token usage per unit time.
    ("faithfulness",       lambda judge: FaithfulnessMetric(threshold=0.5, model=judge, include_reason=True, async_mode=False)),
    ("answer_relevancy",   lambda judge: AnswerRelevancyMetric(threshold=0.5, model=judge, include_reason=True, async_mode=False)),
    ("context_precision",  lambda judge: ContextualPrecisionMetric(threshold=0.5, model=judge, include_reason=True, async_mode=False)),
    ("context_recall",     lambda judge: ContextualRecallMetric(threshold=0.5, model=judge, include_reason=True, async_mode=False)),
]

# ---------------------------------------------------------------------------
# EVAL DATASET
# 10 compliance-domain questions with manually written ground truth answers.
# Ground truth is set by human inspection, NOT auto-labelled from model output.
# (In-Domain Scenario Suite only — Suites 2/3 not yet implemented, see docstring.)
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
    - a_generate() falls back to generate() — the pattern DeepEval docs
      recommend for non-async providers.
    - temperature=0.0 for deterministic judgments.
    - max_tokens=2048 — DeepEval's internal prompts return structured JSON
      with reasoning chains; 16 tokens (our old limit, back in the custom
      implementation) was truncating them.
    - v2: unexpected errors are now logged AND re-raised, instead of being
      swallowed into a fake "{}" / "" response. A silently "successful"
      empty response is how a real failure turns into a misleadingly
      confident score (e.g. an empty claims list reading as vacuously
      faithful = 1.0). Let it fail loudly; the per-metric handler in
      score_with_deepeval() catches it and records it as a real error.
    """

    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self._client = Groq(api_key=api_key)
        super().__init__(model_name)

    def load_model(self):
        return self.model_name

    def _log_rate_limit_headers(self, headers, prefix="    [judge]") -> None:
        # v4: stop guessing. Groq returns the ACTUAL remaining budget on
        # every response (success or 429) via these headers. Print them so
        # we can see real numbers instead of inferring from symptoms.
        if not headers:
            print(f"{prefix} (no rate-limit headers available on this response)")
            return
        keys = [
            "retry-after",
            "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "x-ratelimit-reset-requests",
            "x-ratelimit-limit-tokens",   "x-ratelimit-remaining-tokens",   "x-ratelimit-reset-tokens",
        ]
        found = {k: headers.get(k) for k in keys if headers.get(k) is not None}
        if found:
            print(f"{prefix} rate-limit state: {found}")
        else:
            print(f"{prefix} (rate-limit headers present but none of the expected keys were found — "
                  f"raw keys: {list(headers.keys())})")

    def generate(self, prompt: str, schema=None) -> str:
        import groq

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
                # v4: log remaining budget on the RAW response too, when the
                # SDK exposes it, so we can watch the number decrease across
                # calls instead of only finding out once it hits zero.
                raw_headers = getattr(getattr(response, "_response", None), "headers", None) \
                    or getattr(getattr(response, "response", None), "headers", None)
                if raw_headers:
                    self._log_rate_limit_headers(raw_headers, prefix="    [judge] (ok)")
                return response.choices[0].message.content
            except groq.RateLimitError as e:
                # v4: read the REAL retry-after / reset-tokens values Groq
                # sends back instead of a blind flat 35s guess. Fall back to
                # 35s only if the response genuinely gives us nothing to
                # work with.
                headers = getattr(getattr(e, "response", None), "headers", None)
                self._log_rate_limit_headers(headers)

                wait_time = 35.0
                if headers:
                    retry_after = headers.get("retry-after")
                    reset_tokens = headers.get("x-ratelimit-reset-tokens")
                    if retry_after is not None:
                        try:
                            wait_time = float(retry_after) + 1.0  # +1s safety margin
                        except ValueError:
                            pass
                    elif reset_tokens is not None:
                        try:
                            wait_time = float(reset_tokens) + 1.0
                        except ValueError:
                            pass

                print(f"    [judge] Rate Limit (429) — waiting {wait_time:.1f}s (attempt {attempt+1}/5)...")
                time.sleep(wait_time)
            except Exception as e:
                # v2: don't swallow — log and re-raise so the caller knows
                # this metric genuinely failed rather than silently scoring
                # against an empty/placeholder response.
                print(f"    [judge] Unexpected error: {type(e).__name__}: {str(e)[:120]}")
                raise

        raise RuntimeError(
            f"GroqJudge: all 5 rate-limit retries exhausted for model {self.model_name}"
        )

    async def a_generate(self, prompt: str, schema=None) -> str:
        # DeepEval calls this from async contexts in some metric paths.
        # We delegate to the sync generate() since Groq's async SDK is a
        # different client class. Safe here because Phase 2 below calls
        # m.measure() directly and synchronously, one question at a time,
        # and (v3) async_mode=False on every metric means DeepEval isn't
        # firing concurrent sub-calls into this adapter either — there's
        # no concurrent event loop for this to collide with.
        # NOTE: if this script is ever migrated to DeepEval's evaluate()
        # with AsyncConfig(run_async=True), this blocking-sync-call-behind-
        # an-async-interface pattern needs to be revisited first.
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
) -> tuple[dict, list[dict]]:
    """
    Convert collected records to DeepEval LLMTestCase objects and score them.

    Returns (aggregate_results, per_question_detail) — v2 keeps both instead
    of throwing away everything except the mean.

    Each of the 4 metrics is measured independently per question. If one
    metric errors, the other 3 for that question are NOT discarded — this
    was the single biggest source of misleading zeros in the previous run.

    v3: each metric is constructed with async_mode=False (see METRIC_DEFS),
    so metric.measure() runs its internal sub-steps sequentially instead of
    firing them as concurrent judge calls.
    """
    print(f"\n  [{mode_name}] Scoring {len(records)} responses via DeepEval...")

    metric_keys = [k for k, _ in METRIC_DEFS]
    per_question_detail = []

    for i, rec in enumerate(records):
        q_result = {
            "question": rec["question"],
            "mode": mode_name,
            "status": "scored",
            "metrics": {},
        }

        if not rec["answer"] or not rec["contexts"]:
            print(f"    Q{i+1}: skipped (no answer or no contexts)")
            q_result["status"] = "skipped_no_context"
            for key in metric_keys:
                q_result["metrics"][key] = {"score": None, "success": None, "reason": None, "error": "skipped_no_context"}
            per_question_detail.append(q_result)
            continue

        test_case = LLMTestCase(
            input=rec["question"],
            actual_output=rec["answer"],
            expected_output=rec["ground_truth"],    # required for Recall & Precision
            retrieval_context=rec["contexts"],
        )

        score_strs = []
        any_error = False

        for metric_idx, (key, make_metric) in enumerate(METRIC_DEFS):
            metric = make_metric(judge)
            try:
                metric.measure(test_case)
                score = round(metric.score, 4) if metric.score is not None else None
                q_result["metrics"][key] = {
                    "score": score,
                    "success": metric.success,
                    "reason": metric.reason,
                    "error": None,
                }
                score_strs.append(f"{key.split('_')[0][:5]}={score:.2f}" if score is not None else f"{key}=None")
            except Exception as e:
                any_error = True
                err = f"{type(e).__name__}: {str(e)[:150]}"
                print(f"    Q{i+1}: [{key}] DeepEval error — {err}")
                q_result["metrics"][key] = {"score": None, "success": None, "reason": None, "error": err}
                score_strs.append(f"{key}=ERR")

            # v2: actually sleep between metric calls (this was the gap
            # between the old docstring's claim and what the code did).
            time.sleep(INTER_METRIC_SLEEP)

        if any_error:
            q_result["status"] = "partial_error"

        print(f"    Q{i+1}: " + "  ".join(score_strs))
        per_question_detail.append(q_result)

        if i < len(records) - 1:
            time.sleep(INTER_QUESTION_SLEEP)

    def mean(key):
        vals = [q["metrics"][key]["score"] for q in per_question_detail if q["metrics"][key]["score"] is not None]
        valid = len(vals)
        total = len(per_question_detail)
        avg = round(sum(vals) / valid, 4) if valid else None
        return avg, valid, total

    aggregate = {}
    for key in metric_keys:
        avg, valid, total = mean(key)
        aggregate[key] = {"mean": avg, "valid_count": valid, "total_count": total}

    return aggregate, per_question_detail


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("Lab 7.5 — RAG Evaluation (DeepEval) — v4")
    print(f"Questions  : {len(EVAL_QUESTIONS)}")
    print(f"Namespace  : {NAMESPACE}")
    print(f"Modes      : {', '.join(MODE_NAMES)}")
    print(f"Judge LLM  : {JUDGE_MODEL_NAME}")
    print(f"Gen LLM    : {LLM_CONFIG['model']}")

    groq_api_key = LLM_CONFIG.get("groq_key") or os.environ.get("GROQ_API_KEY", "")
    if not groq_api_key:
        raise ValueError(
            "GROQ_API_KEY not found. Set it in .env.local or as an env var."
        )

    judge = GroqJudge(model_name=JUDGE_MODEL_NAME, api_key=groq_api_key)

    # v4: check the hypothesis directly instead of guessing. If generation
    # and judging share a model (or Groq's free tier enforces an
    # account-wide cap rather than a strict per-model one), Phase 1's ~20
    # generation calls can exhaust the budget before Phase 2 ever calls
    # the judge — which matches the "fails on Q1, attempt 1" signature.
    gen_model = LLM_CONFIG.get("model")
    if gen_model == JUDGE_MODEL_NAME:
        print(f"\n  ⚠ WARNING: generation model and judge model are BOTH "
              f"'{gen_model}'. Phase 1's generation calls and Phase 2's "
              f"judge calls compete for the exact same rate-limit budget. "
              f"This is the most likely cause if 429s appear immediately "
              f"in Phase 2.")
    else:
        print(f"\n  Generation model ({gen_model}) and judge model "
              f"({JUDGE_MODEL_NAME}) are different — if 429s still appear "
              f"immediately in Phase 2, Groq's free tier is likely "
              f"enforcing an account-wide cap rather than a strict "
              f"per-model one.")

    pool = await create_pool()
    all_records: dict[str, list[dict]] = {}
    all_results: dict[str, dict] = {}
    all_detail: list[dict] = []

    try:
        print("\n" + "=" * 60)
        print("PHASE 1: Data Collection (retrieval + LLM generation)")
        print("=" * 60)
        for config, name in zip(MODES, MODE_NAMES):
            all_records[name] = await collect_for_mode(pool, config, name)
    finally:
        await pool.close()

    # v4: cooldown between Phase 1 (generation) and Phase 2 (scoring). We
    # previously assumed these were independent because they're logically
    # separate phases — but that's an assumption, not something we'd
    # verified against the actual shared rate-limit pool. The "fails on
    # Q1/attempt 1" signature is exactly what you'd see if this gap didn't
    # exist and Phase 1 alone used up the budget.
    print(f"\n  Cooling down {INTER_MODE_SLEEP}s before Phase 2 "
          f"(Phase 1 generation calls may share the judge's rate-limit pool)...")
    time.sleep(INTER_MODE_SLEEP)

    print("\n" + "=" * 60)
    print("PHASE 2: Scoring (DeepEval — 4 metrics)")
    print("=" * 60)
    for idx, name in enumerate(MODE_NAMES):
        aggregate, detail = score_with_deepeval(all_records[name], name, judge)
        all_results[name] = aggregate
        all_detail.extend(detail)

        # v3: cooldown between modes. Both modes hit the same judge model's
        # rate-limit pool back to back with zero gap previously — this lets
        # the rolling TPM window clear before the next mode starts.
        if idx < len(MODE_NAMES) - 1:
            print(f"\n  Cooling down {INTER_MODE_SLEEP}s before next mode "
                  f"(shared judge rate-limit pool)...")
            time.sleep(INTER_MODE_SLEEP)

    # Summary table — now shows validity counts, not just a number that
    # might silently include errors as zeros.
    print("\n" + "=" * 74)
    print("FINAL RESULTS")
    print("=" * 74)
    print(f"{'Metric':<20} {'hybrid_rrf':>22} {'hybrid+rerank':>24}")
    print("-" * 74)
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        row = f"{metric:<20}"
        for name in MODE_NAMES:
            r = all_results.get(name, {}).get(metric, {})
            mean_val = r.get("mean")
            valid, total = r.get("valid_count", 0), r.get("total_count", 0)
            cell = f"{mean_val:.4f} ({valid}/{total})" if mean_val is not None else f"N/A ({valid}/{total})"
            row += f"  {cell:>20}"
        print(row)

    print(f"\n  Target faithfulness   : >= 0.85")
    print(f"  Target context_recall : >= 0.80")
    print("  (mean excludes errored/skipped questions — check valid/total before trusting a mean)")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "lab":            "7.5 — RAG Evaluation",
        "framework":      "deepeval",
        "script_version": "v4",
        "judge_llm":      JUDGE_MODEL_NAME,
        "generation_llm": LLM_CONFIG["model"],
        "namespace":      NAMESPACE,
        "top_k":          TOP_K,
        "dataset_size":   len(EVAL_QUESTIONS),
        "corpus":         "enterprise_compliance (GDPR/CCPA/HIPAA)",
        "targets":        {"faithfulness": 0.85, "context_recall": 0.80},
        "results":        all_results,       # aggregate means + validity counts
        "per_question":   all_detail,        # v2: full detail, incl. reasons/errors
        "questions":      [q["question"] for q in EVAL_QUESTIONS],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\n  Saved → {OUTPUT_PATH}  (now includes per-question reasons/errors)")


if __name__ == "__main__":
    asyncio.run(main())
"""
scripts/lab_7.5_deepeval_v5.py
======================================
RAG Evaluation using DeepEval — Gemini for BOTH generation and judging.

Rewritten from v4 to fix the actual causes of the repeated rate-limit / cost
exhaustion, not just symptoms:

  1. No resumability. PROGRESS_FILE existed in v4 but was never read or
     written. Every crash or 429 meant re-running everything from question 1
     — this is almost certainly why repeated runs burned through the budget,
     more than any single run's own inefficiency.
  2. Generation calls had zero pacing. Only the judge had a retry/backoff
     loop; generate_with_citations() was called back-to-back with no limiter
     at all, even though it shares the same Gemini project quota as judging.
  3. The same question was embedded twice (once per retrieval mode) even
     though the embedding doesn't depend on the mode.
  4. No pre-flight cost/call estimate. v4 (and the chat transcript analyzing
     it) guessed at call counts and per-token pricing rather than measuring.
  5. ContextualPrecision/Recall were scored against empty retrieval context
     on retrieval misses and folded into the average as a plain 0.0 —
     conflating "nothing to measure" with "measured and scored badly."
  6. [Found via the first real dry run, 2026-07-27] The generation cost was
     silently going through the length-based ESTIMATE path even though real
     usage was available, because generate_with_citations() returns a flat,
     LiteLLM-style usage dict — prompt_tokens/completion_tokens sit at the
     TOP LEVEL of _meta, not nested under "usage" or "usageMetadata" like
     the code guessed. Confirmed from the actual dry-run output:
       {'completion_tokens': 1669, 'prompt_tokens': 1145, ...,
        'completion_tokens_details': CompletionTokensDetailsWrapper(
            reasoning_tokens=811, text_tokens=858, ...), ...}
     The estimate fallback only measures the visible answer text, so it was
     missing the ~811 hidden reasoning tokens entirely (49% of this sample's
     output) — those bill at the same output rate as visible text per
     Google's pricing page ("Output price (including thinking tokens)"), so
     the old code was undercounting real generation spend. Fixed below by
     falling back to `_meta` itself when neither "usage" nor "usageMetadata"
     is present, and the discrepancy is now surfaced with a print instead of
     failing silently.

Gaps that could NOT be verified from this file alone — flagged, not silently
assumed:
  - embed_query / retrieve / create_pool are imported, not shown here. Their
    internals may already retry or rate-limit. This script paces its own
    calls on top regardless, which is safe either way but could double up on
    throttling if they already do this.
  - [RESOLVED 2026-07-27] generate_with_citations()'s second return value:
    confirmed via the real dry run to be a flat LiteLLM-style usage dict
    with prompt_tokens/completion_tokens at the top level. Wired in below —
    see fix #6 above.
  - [RESOLVED 2026-07-27] Per-token Gemini pricing: verified live against
    https://ai.google.dev/gemini-api/docs/pricing (standard tier, prompts
    <=200K tokens). Both entries in MODEL_PRICING match Google's page
    exactly as of today. Reverify at that link before trusting
    MAX_RUN_COST_USD as a guarantee on any future run, since Google ships
    new models/prices often — e.g. gemini-3.6-flash launched 2026-07-21 at
    $1.50/$7.50, cheaper on output than 3.5 Flash, if you ever want to swap.
  - GEMINI_RPM_CAP is a conservative starting point, not your account's
    measured quota — check AI Studio -> your project -> Quotas. The limiter
    also backs off adaptively on real 429s rather than trusting any static
    table (the earlier analysis of v4 cited Gemini 1.5 Flash/Pro rate limits;
    those models return 404 now, so that table was already stale).

Usage:
  1. Leave DRY_RUN = True and run once more (yes, again — the previous dry
     run's cost number was computed via the broken estimate path from fix
     #6 above, so it likely UNDERCOUNTS real generation cost; you want a
     number from the fixed code before trusting it). It executes ONE record
     (1 question, 1 mode) through generation + all 4 metrics, prints real
     measured cost per call, and extrapolates a projection for the full run.
     Nothing else runs.
  2. Read the projection. Adjust MAX_RUN_COST_USD / GEMINI_RPM_CAP if needed.
  3. Set DRY_RUN = False and run for real. If it dies partway through
     (429s, network blip, ctrl-C), just run it again — it resumes from
     benchmarks/.eval_progress_v5.json instead of starting over.
"""

import asyncio
import json
import sys
import time
import urllib.request
import urllib.error
from collections import deque
from pathlib import Path
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
from config import LLM_CONFIG

# ---------------------------------------------------------------------------
# CONFIG — sanity-check every number here before a real run. See docstring
# above for what's verified vs. estimated.
# ---------------------------------------------------------------------------
GENERATION_MODEL = "gemini/gemini-3.5-flash"   # unchanged from v4 — current, real, GA model
JUDGE_MODEL_NAME = "gemini-2.5-pro"             # unchanged from v4

LLM_CONFIG["model"] = GENERATION_MODEL
GEN_MODEL = LLM_CONFIG["model"]

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_KEY:
    GEMINI_KEY = LLM_CONFIG.get("gemini_key", "") or os.environ.get("GOOGLE_API_KEY", "")
if GEMINI_KEY:
    os.environ["GEMINI_API_KEY"] = GEMINI_KEY
    os.environ["GOOGLE_API_KEY"] = GEMINI_KEY

TOP_K = 5
OUTPUT_PATH = Path("benchmarks/lab_7.5_deepeval_v5.json")
PROGRESS_FILE = Path("benchmarks/.eval_progress_v5.json")

# Conservative starting point — verify your project's actual quota in AI
# Studio. The limiter tightens itself further on real 429s regardless.
GEMINI_RPM_CAP = 40

# Hard circuit breaker. Set this from the dry-run projection, not a guess.
MAX_RUN_COST_USD = 5.00

# $ / 1,000,000 tokens (input / output). Verified live against
# https://ai.google.dev/gemini-api/docs/pricing on 2026-07-27 (standard
# tier, prompts <=200K tokens) — both entries below match Google's page
# exactly. Google's page explicitly states output price "includ[es]
# thinking tokens" for both models, i.e. hidden reasoning tokens bill at
# the same output rate as visible text — no separate line item needed.
# Reverify at the link above before a future run, since Google ships new
# models/prices often (e.g. gemini-3.6-flash launched 2026-07-21 at
# $1.50/$7.50 — cheaper output than 3.5 Flash — if you want a lower-cost
# swap later).
MODEL_PRICING = {
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},   # <=200K context tier
}

DRY_RUN = True  # flip to False only after reading the dry-run projection

MODES = [
    RetrieverConfig(top_k=TOP_K, mode="hybrid", rerank=False),
    RetrieverConfig(top_k=TOP_K, mode="hybrid", rerank=True),
]
MODE_NAMES = ["hybrid_rrf", "hybrid_rrf_reranked"]

# ---------------------------------------------------------------------------
# EVAL DATASET — unchanged from v4
# ---------------------------------------------------------------------------
EVAL_QUESTIONS = [
    # ------------------ LEGAL (GDPR/CCPA) — in_domain ------------------
    {
        "namespace": "legal",
        "type": "in_domain",
        "question": "What rights do individuals have under GDPR regarding their personal data?",
        "ground_truth": "Under GDPR, individuals have the right to access their personal data, the right to rectification of inaccurate data, the right to erasure (right to be forgotten), the right to restrict processing, the right to data portability, and the right to object to processing. They also have rights related to automated decision-making and profiling.",
    },
    {
        "namespace": "legal",
        "type": "in_domain",
        "question": "What is the maximum fine for a serious GDPR violation?",
        "ground_truth": "The maximum fine for a serious GDPR violation is 20 million euros or 4% of the company's total global annual turnover of the preceding financial year, whichever is higher.",
    },
    {
        "namespace": "legal",
        "type": "in_domain",
        "question": "What constitutes personal data under GDPR?",
        "ground_truth": "Personal data under GDPR is any information relating to an identified or identifiable natural person. This includes names, identification numbers, location data, online identifiers, and factors specific to the physical, physiological, genetic, mental, economic, cultural, or social identity of that person.",
    },
    {
        "namespace": "legal",
        "type": "in_domain",
        "question": "What does CCPA require companies to disclose to California consumers?",
        "ground_truth": "CCPA requires companies to disclose to California consumers the categories of personal information collected, the purposes for which it is used, the categories of third parties with whom it is shared, and the consumer's rights including the right to know, delete, and opt-out of the sale of their personal information.",
    },
    {
        "namespace": "legal",
        "type": "in_domain",
        "question": "What are the key principles of data minimisation under GDPR?",
        "ground_truth": "Data minimisation under GDPR requires that personal data collected must be adequate, relevant, and limited to what is necessary in relation to the purposes for which it is processed. Controllers should not collect more data than strictly required.",
    },
    # ------------------ KYC/AML — in_domain ------------------
    {
        "namespace": "kyc_aml",
        "type": "in_domain",
        "question": "Under 31 CFR 1010.230, what constitutes a beneficial owner of a legal entity customer?",
        "ground_truth": "A beneficial owner is any individual who owns 25 percent or more of the equity interests of a legal entity customer, and a single individual with significant responsibility to control, manage, or direct the legal entity customer.",
    },
    {
        "namespace": "kyc_aml",
        "type": "in_domain",
        "question": "What is the threshold for filing a Currency Transaction Report (CTR) by a financial institution?",
        "ground_truth": "A financial institution must file a report of each deposit, withdrawal, exchange of currency or other payment or transfer, by, through, or to such financial institution which involves a transaction in currency of more than $10,000.",
    },
    {
        "namespace": "kyc_aml",
        "type": "in_domain",
        "question": "What are the record retention requirements for customer identification programs under the Bank Secrecy Act?",
        "ground_truth": "A covered financial institution must retain the identifying information obtained about the customer for five years after the date the account is closed.",
    },
    {
        "namespace": "kyc_aml",
        "type": "in_domain",
        "question": "How long does a bank have to file a Suspicious Activity Report (SAR) after becoming aware of a suspicious transaction?",
        "ground_truth": "A bank must file a SAR no later than 30 calendar days after the date of initial detection of facts that may constitute a basis for filing a SAR. If no suspect was identified on the date of detection, the bank may delay filing for an additional 30 calendar days, but in no case shall reporting be delayed more than 60 calendar days.",
    },
    {
        "namespace": "kyc_aml",
        "type": "in_domain",
        "question": "Can a financial institution notify the subject of a Suspicious Activity Report (SAR) that a SAR has been filed?",
        "ground_truth": "No, a financial institution, and its directors, officers, employees, and agents, are strictly prohibited from disclosing to the subject of a SAR or any other person that a SAR has been prepared or filed.",
    },
    # ------------------ OOD TRIPLETS — ood (exact-match refusal check only) --
    {
        "namespace": "legal",
        "type": "ood",
        "question": "What is the capital of France?",
        "ground_truth": "I do not have sufficient information in the provided context to answer this query.",
    },
    {
        "namespace": "kyc_aml",
        "type": "ood",
        "question": "How many calories are in an apple?",
        "ground_truth": "I do not have sufficient information in the provided context to answer this query.",
    },
    {
        "namespace": "kyc_aml",
        "type": "ood",
        "question": "What are the rules for adopting a pet in California?",
        "ground_truth": "I do not have sufficient information in the provided context to answer this query.",
    },
]


def _approx_tokens(s: str) -> int:
    """Rough ~4-chars/token heuristic. Only used for the generation cost
    estimate when generate_with_citations() doesn't yield usable usage — see
    fix #6 in the module docstring for why this path underestimates cost
    (it only sees visible answer text, not hidden reasoning tokens)."""
    return max(1, len(s) // 4)


# ---------------------------------------------------------------------------
# Rate limiting + cost guard — shared across generation AND judging, since
# both draw on the same Gemini project quota. This is the main structural
# fix over v4, which only throttled (inconsistently) the judge path.
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._timestamps = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] > 60:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_per_minute:
                wait = 60 - (now - self._timestamps[0]) + 0.1
                print(f"    [rate-limiter] at {self.max_per_minute} RPM cap, waiting {wait:.1f}s")
                await asyncio.sleep(max(wait, 0))
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] > 60:
                    self._timestamps.popleft()
            self._timestamps.append(now)

    def throttle_down(self):
        """Called on a real 429. Tightens the cap for the rest of this run
        instead of trusting the configured number any further."""
        old = self.max_per_minute
        self.max_per_minute = max(5, int(self.max_per_minute * 0.6))
        print(f"    [rate-limiter] 429 received — cap lowered {old} -> {self.max_per_minute} RPM")


class CostGuard:
    """Hard circuit breaker on cumulative spend. Trips the run rather than
    let a bug, a retry storm, or a wrong assumption burn past what you
    approved in the dry run.

    `verbose` (on by default during DRY_RUN — see main()) prints every
    priced call as it happens, tagged with the `note` the caller passed in.
    This is what would have caught fix #6 immediately: the previous dry run
    silently used the estimate path and nothing surfaced that fact anywhere
    in the printed output. Now it does.
    """

    def __init__(self, max_usd: float, verbose: bool = False):
        self.max_usd = max_usd
        self.spent_usd = 0.0
        self.calls = 0
        self.verbose = verbose
        self.call_log = []  # [(model, input_tokens, output_tokens, cost, note), ...]

    def record(self, model: str, input_tokens: int, output_tokens: int, note: str = ""):
        price = MODEL_PRICING.get(model)
        if price is None:
            print(f"    [cost-guard] no pricing entry for '{model}' — spend NOT being tracked for this call ({note})")
            return
        cost = (input_tokens / 1_000_000) * price["input"] + (output_tokens / 1_000_000) * price["output"]
        self.spent_usd += cost
        self.calls += 1
        self.call_log.append((model, input_tokens, output_tokens, cost, note))
        if self.verbose:
            tag = f" [{note}]" if note else ""
            print(f"    [cost-guard]{tag} {model}: {input_tokens} in / {output_tokens} out tokens "
                  f"-> ${cost:.4f} (running total ${self.spent_usd:.4f})")
        if self.spent_usd >= self.max_usd:
            raise RuntimeError(
                f"CostGuard tripped: ${self.spent_usd:.4f} >= ${self.max_usd:.2f} cap after "
                f"{self.calls} priced calls. Halting before spending more. Don't just raise "
                f"MAX_RUN_COST_USD — first check why the run is costing more than the dry-run "
                f"projection said it would."
            )

    def summary(self) -> str:
        return f"{self.calls} priced calls, ${self.spent_usd:.4f} spent"


# ---------------------------------------------------------------------------
# Checkpointing — the actual fix for "repeated runs exhausted the budget."
# Every generated record and every judged metric is persisted immediately,
# so a crash or a deliberate stop loses at most the call in flight.
# ---------------------------------------------------------------------------
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text())
        except json.JSONDecodeError:
            print("    [!] progress file was corrupt — starting fresh")
    return {"generation": {}, "judging": {}}


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(progress, indent=2))
    tmp.replace(PROGRESS_FILE)


class GeminiJudge(DeepEvalBaseLLM):
    def __init__(self, model_name: str, api_key: str, rate_limiter: RateLimiter, cost_guard: CostGuard):
        self.model_name = model_name
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self.cost_guard = cost_guard
        super().__init__(model_name)

    def load_model(self):
        return self.model_name

    def _generate_sync(self, prompt: str, schema=None) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0},
        }
        if schema is not None:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    usage = res.get("usageMetadata", {})
                    self.cost_guard.record(
                        self.model_name,
                        usage.get("promptTokenCount", 0),
                        usage.get("candidatesTokenCount", 0),
                        note="judge",
                    )
                    return res["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    error_body = str(e)
                if e.code == 429 or "RESOURCE_EXHAUSTED" in error_body:
                    self.rate_limiter.throttle_down()
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    wait = float(retry_after) if retry_after else 30.0
                    print(f"    [gemini-judge] 429 — backing off {wait:.0f}s (attempt {attempt+1}/4)")
                else:
                    print(f"    [gemini-judge] HTTP {e.code}: {error_body[:200]}")
                    wait = 10.0
                time.sleep(wait)
            except Exception as e:
                print(f"    [gemini-judge] unexpected error: {e} — retrying in 10s")
                time.sleep(10.0)

        return "{}" if schema is not None else ""

    async def a_generate(self, prompt: str, schema=None) -> str:
        await self.rate_limiter.acquire()
        # Runs the blocking call off the event loop via a worker thread instead
        # of a synchronous time.sleep()/urlopen() inline. Note: this script is
        # fully sequential (no concurrent tasks running alongside it), so this
        # is a correctness cleanup, not a throughput fix — the real fix for
        # rate-limit exhaustion is the RateLimiter/CostGuard above, not this.
        return await asyncio.to_thread(self._generate_sync, prompt, schema)

    def generate(self, prompt: str, schema=None) -> str:
        return self._generate_sync(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name


# ---------------------------------------------------------------------------
# Generation + retrieval
# ---------------------------------------------------------------------------
_embedding_cache: dict = {}


async def get_cached_embedding(question: str):
    """The retrieval query text is identical across both modes (only the
    rerank flag differs) — embedding it twice per question was pure waste.
    This halves embedding calls for the full run (26 -> 13)."""
    if question not in _embedding_cache:
        _embedding_cache[question] = await embed_query(question)
    return _embedding_cache[question]


async def collect_for_mode(pool, config: RetrieverConfig, mode_name: str,
                            rate_limiter: RateLimiter, cost_guard: CostGuard,
                            progress: dict, question_limit: int = None,
                            persist: bool = True) -> list:
    questions = EVAL_QUESTIONS if question_limit is None else EVAL_QUESTIONS[:question_limit]
    print(f"\n  [{mode_name}] Collecting {len(questions)} answers...")
    records = []
    gen_progress = progress["generation"].setdefault(mode_name, {})

    from api.services.llm import generate_with_citations

    for i, item in enumerate(questions):
        key = str(i)
        if key in gen_progress:
            records.append(gen_progress[key])
            print(f"    Q{i+1}: (resumed from checkpoint)")
            continue

        question = item["question"]
        ground_truth = item["ground_truth"]
        namespace = item["namespace"]

        embedding = await get_cached_embedding(question)
        chunks = await retrieve(
            pool=pool,
            query=question,
            query_embedding=embedding,
            namespace=namespace,
            cfg=config,
        )

        if not chunks:
            record = {
                "question": question,
                "answer": "I do not have sufficient information in the provided context to answer this query.",
                "contexts": [],
                "ground_truth": ground_truth,
                "type": item.get("type", "in_domain"),
            }
        else:
            db_chunks = [
                {
                    "document_id": c["document_id"],
                    "source_filename": c.get("source_filename") or "unknown",
                    "text": c["content"],
                    "score": (
                        c["rrf_score"] if "rrf_score" in c else
                        c["vector_score"] if "vector_score" in c else
                        c["bm25_score"] if "bm25_score" in c else
                        0.0
                    ),
                }
                for c in chunks
            ]

            eval_query = (
                "INSTRUCTION: If the answer is not explicitly stated in the provided context, "
                "you must output exactly: 'I do not have sufficient information in the provided "
                f"context to answer this query.'\n\nQUESTION: {question}"
            )

            await rate_limiter.acquire()
            is_error = False
            try:
                answer_obj, _meta = await generate_with_citations(eval_query, db_chunks)
                answer = answer_obj.answer

                # Confirmed shape (from a real dry run, 2026-07-27): _meta is a
                # flat, LiteLLM-style usage dict — prompt_tokens/completion_tokens
                # sit at the TOP LEVEL, not nested under "usage"/"usageMetadata".
                # The nested-key checks are kept as safety nets in case that
                # shape ever changes upstream; the real fallback is `_meta`
                # itself, which is what actually matches today.
                real_in = real_out = None
                if isinstance(_meta, dict):
                    usage = _meta.get("usage") or _meta.get("usageMetadata") or _meta
                    real_in = usage.get("prompt_tokens", usage.get("promptTokenCount"))
                    real_out = usage.get("completion_tokens", usage.get("candidatesTokenCount"))

                if DRY_RUN:
                    print(f"    [dry-run] generate_with_citations() metadata: {_meta!r}")
                    details = _meta.get("completion_tokens_details") if isinstance(_meta, dict) else None
                    reasoning_tok = getattr(details, "reasoning_tokens", None) if details is not None else None
                    text_tok = getattr(details, "text_tokens", None) if details is not None else None
                    if reasoning_tok is not None:
                        print(f"    [dry-run] of {real_out} completion tokens: ~{reasoning_tok} were hidden "
                              f"reasoning tokens, ~{text_tok} were visible answer text. Both bill at the "
                              f"output rate — see 'Output price (including thinking tokens)' at "
                              f"ai.google.dev/gemini-api/docs/pricing.")

                if real_in is not None and real_out is not None:
                    cost_guard.record(GEN_MODEL.split("/")[-1], real_in, real_out, note="generation (measured)")
                else:
                    # This is the failure mode fix #6 caught: falling back here
                    # means the answer's hidden reasoning tokens go untracked.
                    print(f"    [!] Q{i+1}: no usable token usage in _meta — cost tracked via a length "
                          f"estimate instead (less accurate, likely UNDERcounts hidden reasoning tokens)")
                    approx_in = _approx_tokens(eval_query) + sum(_approx_tokens(c["text"]) for c in db_chunks)
                    approx_out = _approx_tokens(answer)
                    cost_guard.record(GEN_MODEL.split("/")[-1], approx_in, approx_out,
                                       note="generation (estimated — no usage found in _meta)")
            except Exception as e:
                # Tag the answer so a generation failure is distinguishable from
                # a real (low-quality) answer in the output. Set is_error=True
                # so the judging loop skips this record entirely rather than
                # scoring the error string as if it were a real answer.
                answer = f"[GENERATION_ERROR] {e}"
                is_error = True
                print(f"    [!] Q{i+1} generation failed: {e}")

            record = {
                "question": question,
                "answer": answer,
                "contexts": [c["content"] for c in chunks],
                "ground_truth": ground_truth,
                "generation_failed": is_error,
                "type": item.get("type", "in_domain"),
            }

        print(f"    Q{i+1}: done  chunks={len(record['contexts'])}  ({namespace})")
        records.append(record)
        gen_progress[key] = record
        if persist:
            save_progress(progress)

    return records


# ---------------------------------------------------------------------------
# Dry run — measures ONE record's real cost/calls before committing to the
# full run. This replaces guessed call counts and guessed pricing with an
# actual number from your actual deployment.
# ---------------------------------------------------------------------------
async def run_dry_run(pool, rate_limiter, cost_guard, metrics):
    print("\n" + "=" * 70)
    print("DRY RUN — 1 question, 1 mode, full pipeline (generation + all 4 metrics)")
    print("=" * 70)

    throwaway_progress = {"generation": {}, "judging": {}}
    records = await collect_for_mode(
        pool, MODES[0], "dryrun_sample", rate_limiter, cost_guard, throwaway_progress,
        question_limit=1, persist=False,
    )
    record = records[0]

    tc = LLMTestCase(
        input=record["question"],
        actual_output=record["answer"],
        retrieval_context=record["contexts"],
        expected_output=record["ground_truth"],
    )

    print("\n  Sample record:")
    print(f"    Q:  {record['question']}")
    print(f"    A:  {record['answer'][:400]}{'...' if len(record['answer']) > 400 else ''}")
    print(f"    GT: {record['ground_truth'][:300]}")
    print(f"    Retrieved {len(record['contexts'])} context chunk(s)")

    print("\n  Metric results (READ THESE before trusting the cost projection below —")
    print("  this is the part that tells you whether the judge is actually accurate):")
    for m in metrics:
        try:
            await m.a_measure(tc)
            score = getattr(m, "score", None)
            success = getattr(m, "success", None)
            reason = getattr(m, "reason", None)
            print(f"    {m.__name__}: score={score} success={success}")
            if reason:
                print(f"      reason: {reason}")
        except Exception as e:
            print(f"    [!] {m.__name__} failed during dry run: {e}")

    total_records = len(EVAL_QUESTIONS) * len(MODES)
    per_record_cost = cost_guard.spent_usd
    projected_total = per_record_cost * total_records

    print("\n" + "-" * 70)
    print("COST PROJECTION (extrapolated from 1 sample — expect real variance)")
    print(f"  Sample cost (1 generation + 4 metrics): ${per_record_cost:.4f} ({cost_guard.calls} priced calls)")
    print(f"  Full run = {total_records} records ({len(EVAL_QUESTIONS)} questions x {len(MODES)} modes)")
    print(f"  Projected total cost: ${projected_total:.2f}")
    print(f"  Your MAX_RUN_COST_USD guard: ${MAX_RUN_COST_USD:.2f}")
    if projected_total > MAX_RUN_COST_USD:
        print("  >>> Projection EXCEEDS the cost guard — the real run would halt partway through.")
        print("      Raise MAX_RUN_COST_USD deliberately, or trim the question/metric set.")
    else:
        print("  >>> Projection is within the cost guard.")
    print("-" * 70)
    print("\nDon't flip DRY_RUN off on cost alone — check that the metric scores above")
    print("look sane first (e.g. Faithfulness/AnswerRelevancy near 1.0 for a correctly")
    print("grounded in-domain answer). A cheap run that scores wrong isn't a win.")
    print("Set DRY_RUN = False at the top of the file to run for real.")


# ---------------------------------------------------------------------------
async def main():
    pool = await create_pool()

    rate_limiter = RateLimiter(GEMINI_RPM_CAP)
    cost_guard = CostGuard(MAX_RUN_COST_USD, verbose=DRY_RUN)
    judge = GeminiJudge(JUDGE_MODEL_NAME, GEMINI_KEY, rate_limiter, cost_guard)

    metrics = [
        FaithfulnessMetric(model=judge, threshold=0.7),
        AnswerRelevancyMetric(model=judge, threshold=0.7),
        ContextualPrecisionMetric(model=judge, threshold=0.7),
        ContextualRecallMetric(model=judge, threshold=0.7),
    ]

    if DRY_RUN:
        await run_dry_run(pool, rate_limiter, cost_guard, metrics)
        return

    progress = load_progress()
    all_results = {}

    for config, name in zip(MODES, MODE_NAMES):
        print(f"\n{'=' * 70}\nRUNNING MODE: {name}\n{'=' * 70}")

        records = await collect_for_mode(pool, config, name, rate_limiter, cost_guard, progress)

        in_domain_scores = {type(m).__name__: [] for m in metrics}
        ood_results = []
        judge_progress = progress["judging"].setdefault(name, {})

        print(f"\n  [{name}] Judging...")
        for i, r in enumerate(records):
            key = str(i)
            existing = judge_progress.get(key, {})
            has_context = bool(r["contexts"])

            # Skip judging for records where generation itself failed.
            if r.get("generation_failed"):
                print(f"    -> Q{i+1}: skipping judge — generation failed")
                for m in metrics:
                    existing.setdefault(type(m).__name__, None)
                judge_progress[key] = existing
                save_progress(progress)
                continue

            # OOD questions: exact-match refusal check only — no judge API calls.
            # DeepEval metrics are meaningless here (the answer is a fixed refusal
            # string, not a grounded answer) and would corrupt in-domain averages.
            if r.get("type") == "ood":
                if "ood_pass" in existing:
                    ood_results.append({"question": r["question"], "passed": existing["ood_pass"]})
                    print(f"    -> Q{i+1} [OOD]: (resumed from checkpoint)")
                    continue
                passed = r["answer"].strip() == r["ground_truth"].strip()
                ood_results.append({"question": r["question"], "passed": passed})
                existing["ood_pass"] = passed
                judge_progress[key] = existing
                save_progress(progress)
                print(f"    -> Q{i+1} [OOD]: {'PASS' if passed else 'FAIL'} — {r['question'][:55]}")
                continue

            # In-domain: run all 4 DeepEval metrics.
            tc = LLMTestCase(
                input=r["question"],
                actual_output=r["answer"],
                retrieval_context=r["contexts"],
                expected_output=r["ground_truth"],
            )

            for m in metrics:
                metric_name = type(m).__name__

                if metric_name in existing:
                    if existing[metric_name] is not None:
                        in_domain_scores[metric_name].append(existing[metric_name])
                    continue

                if not has_context and metric_name in ("ContextualPrecisionMetric", "ContextualRecallMetric"):
                    print(f"    -> Q{i+1} {metric_name}: skipped (empty context)")
                    existing[metric_name] = None
                    judge_progress[key] = existing
                    save_progress(progress)
                    continue

                print(f"    -> Judging Q{i+1} [{metric_name}]: {r['question'][:50]}...")
                try:
                    await m.a_measure(tc)
                    existing[metric_name] = m.score
                    in_domain_scores[metric_name].append(m.score)
                except Exception as e:
                    print(f"       [!] {metric_name} failed: {e}")
                    existing[metric_name] = None

                judge_progress[key] = existing
                save_progress(progress)

        n_in_domain = sum(1 for q in EVAL_QUESTIONS if q.get("type") == "in_domain")
        n_ood = sum(1 for q in EVAL_QUESTIONS if q.get("type") == "ood")
        ood_passed = sum(1 for r in ood_results if r["passed"])
        ood_pass_rate = ood_passed / len(ood_results) if ood_results else None

        avg_in_domain = {k: (sum(v) / len(v) if v else None) for k, v in in_domain_scores.items()}
        all_results[name] = {
            "in_domain": avg_in_domain,
            "ood": {
                "pass_rate": ood_pass_rate,
                "passed": ood_passed,
                "total": len(ood_results),
                "detail": ood_results,
            },
        }

        print(f"\n  [{name}] IN-DOMAIN RESULTS ({n_in_domain} questions):")
        for k, v in avg_in_domain.items():
            print(f"    {k}: {v:.3f}" if v is not None else f"    {k}: N/A")

        print(f"\n  [{name}] OOD REFUSAL RESULTS ({n_ood} questions):")
        if ood_pass_rate is not None:
            print(f"    Pass rate: {ood_pass_rate:.0%}  ({ood_passed}/{len(ood_results)} correctly refused)")
        else:
            print(f"    No OOD records evaluated.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n[DONE] Saved results to {OUTPUT_PATH}")
    print(f"[COST] {cost_guard.summary()}")


if __name__ == "__main__":
    asyncio.run(main())
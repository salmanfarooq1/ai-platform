import litellm
import json
from api.models.schemas import GeneratedAnswer, Citation
from config import LLM_CONFIG
import logging

logger = logging.getLogger("api.llm")

# Auto-log all LLM calls — tracks spend, latency, and failure rates
# In production: litellm.success_callback = ["langfuse"]
# For now: custom callback that logs to structured logger
litellm.success_callback = ["log"]
litellm.set_verbose = False  # Turn off LiteLLM's internal debug logging
GENERATION_PROMPT = """You are an expert Q&A system.
Answer the user's question based ONLY on the provided context chunks.
You MUST cite which chunk IDs you used to form your answer.

Context:
{context_with_ids}

Question: {question}
"""

async def generate_with_citations(
    query: str, 
    chunks: list[dict],
    model: str | None = None,
) -> tuple[GeneratedAnswer, dict]:
    """
    Takes a user query and a list of DB chunks. Returns a validated Pydantic object
    and a usage dictionary for the FinOps middleware.
    """
    # 1. Format the chunks so the AI can read them and cite them by ID
    context_with_ids = "\n\n".join([
        f"[chunk_{i}] (from {c['source_filename']}, score {c['score']:.2f}):\n{c['text']}"
        for i, c in enumerate(chunks)
    ])

    model_to_use = model or LLM_CONFIG["model"]

    # 2. Call the LLM via LiteLLM
    response = await litellm.acompletion(
        model=model_to_use,                 # Driven by MODE env var or routing decision
        messages=[{
            "role": "user",
            "content": GENERATION_PROMPT.format(
                context_with_ids=context_with_ids,
                question=query
            )
        }],
        response_format=GeneratedAnswer, # The structured response object
        max_tokens=1000
    )

    # 3. Check if the model was cut off mid-answer by max_tokens.
    # finish_reason == 'length' means the output was truncated, not naturally complete.
    # A truncated JSON string will fail model_validate_json with a cryptic parse error.
    # We surface it explicitly here instead.
    finish_reason = response.choices[0].finish_reason
    if finish_reason == "length":
        logger.warning(
            f"[llm] Response truncated at max_tokens limit. "
            f"model={model_to_use} query='{query[:60]}'"
        )
        raise ValueError(
            f"LLM response was truncated (finish_reason=length). "
            f"Query may require a longer answer. Consider increasing max_tokens or reducing top_k."
        )

    # 4. LiteLLM returns a string containing the JSON. We parse it back into our Pydantic model.
    raw_content = response.choices[0].message.content
    answer_obj = GeneratedAnswer.model_validate_json(raw_content)

    # 5. Map the AI's generic citations (e.g., "chunk_0") back to the real DB records
    hydrated_citations = []
    for cit in answer_obj.citations:
        try:
            idx = cit.chunk_index
            real_chunk = chunks[idx]
            hydrated_citations.append(Citation(
                document_id=real_chunk["document_id"],
                source_filename=real_chunk["source_filename"],
                chunk_index=idx,
                relevance_score=real_chunk["score"],
                excerpt=real_chunk["text"][:100],
            ))
        except (IndexError, TypeError):
            # LLM cited a chunk_index that doesn't exist in the retrieved chunks.
            # Log it so we can track hallucination frequency — silent drops are invisible.
            logger.warning(
                f"[citations] Hallucinated chunk_index={cit.chunk_index} "
                f"(chunks available: {len(chunks)}) "
                f"query='{query[:60]}'"
            )
            continue
            
    answer_obj.citations = hydrated_citations

    # 5. Extract the tokens so our FinOps middleware can charge for it!
    usage_dict = dict(response.usage) if response.usage else {}
    usage_dict["model"] = response.model
    
    return answer_obj, usage_dict

# --- Model Routing ---

# Complexity signals — words that indicate a query needs reasoning, not recall.
# Simple queries are factual lookups: "What is X?", "Define Y", "How long is Z?"
# Complex queries require synthesis: comparisons, tradeoffs, causal reasoning.
COMPLEX_SIGNALS = {
    "compare", "difference", "trade-off", "tradeoff", "analyze", "analyse",
    "explain", "why", "how does", "implications", "architecture", "design",
    "evaluate", "contrast", "relationship", "impact", "consequence",
    "async", "await", "class", "function", "algorithm", "implement",
}

SIMPLE_SIGNALS = {"what is", "define", "who is", "when did", "where is", "list"}


def classify_query_complexity(query: str) -> str:
    """
    Classify query as 'simple' or 'complex' using signal words.

    Heuristic, not ML. Fast and deterministic — no model call needed.
    Default is 'complex': safer to over-provision than under-serve.

    In production this would be replaced by an SLM classifier (a small
    model like phi-3-mini that classifies in ~10ms). Heuristics get you
    80% of the way there for 0% of the cost.

    Why default complex:
    A simple model giving a wrong answer on a complex compliance question
    is worse than a complex model being slightly over-provisioned for a
    simple question. Err toward quality.
    """
    q_lower = query.lower().strip()
    words = set(q_lower.split())
    word_count = len(words)

    # Explicit complex signals override everything
    for signal in COMPLEX_SIGNALS:
        if signal in q_lower:
            return "complex"

    # Short query + simple signal = simple
    if word_count <= 8:
        for signal in SIMPLE_SIGNALS:
            if q_lower.startswith(signal):
                return "simple"

    return "complex"  # safe default


# Model tiers — pulled from config so switching models is one env var change
def _get_model_for_complexity(complexity: str) -> str:
    """
    Map complexity to model.

    Simple → cheapest available (local Ollama = $0.00)
    Complex → best available (configured in LLM_CONFIG)

    Why not hardcode model names here:
    Config already handles local/demo/prod switching. Routing just picks
    which tier — config decides what that tier actually is per environment.
    """
    if complexity == "simple":
        # In local/demo mode this is still Ollama — cost difference is latency
        # In prod mode: groq/llama for simple vs azure/gpt-4o for complex
        fallbacks = LLM_CONFIG.get("fallbacks", [])
        return fallbacks[0] if fallbacks else LLM_CONFIG["model"]
    return LLM_CONFIG["model"]


async def generate_with_routing(
    query: str,
    chunks: list[dict],
    model_override: str | None = None,
) -> tuple[GeneratedAnswer, dict]:
    """
    Route query to appropriate model tier, then generate with citations.

    model_override: admin/testing escape hatch — bypasses routing entirely.
    usage_dict includes routing_decision so FinOps middleware can log it.

    The key insight: embedding is already computed for vector search.
    Classification is pure string ops — microseconds. So routing adds
    ~0ms latency while potentially saving significant cost at scale.
    """
    if model_override:
        complexity = "override"
        model = model_override
    else:
        complexity = classify_query_complexity(query)
        model = _get_model_for_complexity(complexity)

    logger.info(f"[routing] complexity={complexity} model={model} query='{query[:60]}'")

    answer_obj, usage_dict = await generate_with_citations(query, chunks, model=model)

    # Augment usage dict with routing decision for FinOps tracking
    usage_dict["routing_decision"] = complexity
    usage_dict["routed_model"] = model

    return answer_obj, usage_dict
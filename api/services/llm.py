import logging

from pydantic import BaseModel, Field

from config import LLM_CONFIG
from ports import LLMPort

logger = logging.getLogger("api.services.llm")

GENERATION_MAX_TOKENS = 4000  # completion tokens asked for; the gateway counts them against the policy cap

class Citation(BaseModel):
    document_id: str
    source_filename: str = "unknown"
    chunk_index: int
    relevance_score: float
    excerpt: str

class GeneratedAnswer(BaseModel):
    answer: str = Field(description="Direct answer to the user question synthesized ONLY from provided context.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    citations: list[Citation] = Field(description="List of chunk citations used to compose the answer")

GENERATION_PROMPT = """You are a compliance research assistant. Synthesize a concise answer strictly based on the provided context chunks.

Context Chunks:
{context_with_ids}

Question: {question}
"""

async def generate_with_citations(
    llm: LLMPort,
    query: str,
    chunks: list[dict],
    model: str | None = None,
) -> tuple[GeneratedAnswer, dict]:
    context_with_ids = "\n\n".join([
        f"[chunk_{i}] (from {c.get('source_filename') or 'unknown'}, score {c.get('score', 0.0):.2f}):\n{c['text']}"
        for i, c in enumerate(chunks)
    ])

    model_to_use = model or LLM_CONFIG["model"]

    completion = None
    for attempt in range(3):
        try:
            completion = await llm.complete(
                [{
                    "role": "user",
                    "content": GENERATION_PROMPT.format(
                        context_with_ids=context_with_ids,
                        question=query
                    )
                }],
                model=model_to_use,
                max_tokens=GENERATION_MAX_TOKENS,
                response_format=GeneratedAnswer,
            )
            break
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < 2:
                import asyncio
                logger.warning(f"[llm] Rate limited on {model_to_use}, waiting 35s (attempt {attempt + 1})...")
                await asyncio.sleep(35)
            else:
                raise

    if completion is None:  # unreachable: the loop either breaks with a completion or raises
        raise RuntimeError("LLM call returned no response")
    if completion.finish_reason == "length":
        logger.warning(f"[llm] Response truncated at max_tokens limit. model={model_to_use} query='{query[:60]}'")
        raise ValueError("LLM response was truncated (finish_reason=length).")

    answer_obj = GeneratedAnswer.model_validate_json(completion.text)

    hydrated_citations = []
    for cit in answer_obj.citations:
        try:
            idx = cit.chunk_index
            real_chunk = chunks[idx]
            hydrated_citations.append(Citation(
                document_id=real_chunk["document_id"],
                source_filename=real_chunk.get("source_filename") or "unknown",
                chunk_index=idx,
                relevance_score=real_chunk.get("score", 0.0),
                excerpt=real_chunk["text"][:100],
            ))
        except (IndexError, TypeError):
            logger.warning(f"[citations] Hallucinated chunk_index={cit.chunk_index}")
            continue

    answer_obj.citations = hydrated_citations

    usage_dict = {
        "prompt_tokens": completion.tokens_in,
        "completion_tokens": completion.tokens_out,
        "total_cost": completion.cost_usd,
        "routed_model": model_to_use,
        "model": model_to_use,  # FinOps reads this key to price and log the request
    }

    return answer_obj, usage_dict

async def generate_with_routing(
    llm: LLMPort,
    query: str,
    chunks: list[dict],
    model: str | None = None,
) -> tuple[GeneratedAnswer, dict]:
    return await generate_with_citations(llm, query, chunks, model=model)

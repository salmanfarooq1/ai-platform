import json
import logging
from typing import Any
import litellm
from pydantic import BaseModel, Field
from api.models.schemas import SearchResult
from config import LLM_CONFIG, MODEL_PRICING

logger = logging.getLogger("api.services.llm")

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
    query: str,
    chunks: list[dict],
    model: str | None = None,
) -> tuple[GeneratedAnswer, dict]:
    context_with_ids = "\n\n".join([
        f"[chunk_{i}] (from {c.get('source_filename') or 'unknown'}, score {c.get('score', 0.0):.2f}):\n{c['text']}"
        for i, c in enumerate(chunks)
    ])

    model_to_use = model or LLM_CONFIG["model"]

    response = None
    for attempt in range(3):
        try:
            response = await litellm.acompletion(
                model=model_to_use,
                messages=[{
                    "role": "user",
                    "content": GENERATION_PROMPT.format(
                        context_with_ids=context_with_ids,
                        question=query
                    )
                }],
                response_format=GeneratedAnswer,
                max_tokens=4000
            )
            break
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < 2:
                import asyncio
                logger.warning(f"[llm] Rate limited on {model_to_use}, waiting 35s (attempt {attempt + 1})...")
                await asyncio.sleep(35)
            else:
                raise

    finish_reason = response.choices[0].finish_reason
    if finish_reason == "length":
        logger.warning(f"[llm] Response truncated at max_tokens limit. model={model_to_use} query='{query[:60]}'")
        raise ValueError("LLM response was truncated (finish_reason=length).")

    raw_content = response.choices[0].message.content
    answer_obj = GeneratedAnswer.model_validate_json(raw_content)

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

    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

    rates = MODEL_PRICING.get(model_to_use, {"input": 0.0, "output": 0.0})
    llm_cost = (prompt_tokens / 1_000_000) * rates["input"] + (completion_tokens / 1_000_000) * rates["output"]

    usage_dict = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_cost": llm_cost,
        "routed_model": model_to_use,
    }

    return answer_obj, usage_dict

async def generate_with_routing(
    query: str,
    chunks: list[dict],
    model: str | None = None,
) -> tuple[GeneratedAnswer, dict]:
    return await generate_with_citations(query, chunks, model=model)

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

async def generate_with_citations(query: str, chunks: list[dict]) -> tuple[GeneratedAnswer, dict]:
    """
    Takes a user query and a list of DB chunks. Returns a validated Pydantic object
    and a usage dictionary for the FinOps middleware.
    """
    # 1. Format the chunks so the AI can read them and cite them by ID
    context_with_ids = "\n\n".join([
        f"[chunk_{i}] (from {c['source_filename']}, score {c['score']:.2f}):\n{c['text']}"
        for i, c in enumerate(chunks)
    ])

    # 2. Call the LLM via LiteLLM
    response = await litellm.acompletion(
        model=LLM_CONFIG["model"],          # Driven by MODE env var — never hardcoded
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

    # 3. LiteLLM returns a string containing the JSON. We parse it back into our Pydantic model.
    raw_content = response.choices[0].message.content
    answer_obj = GeneratedAnswer.model_validate_json(raw_content)

    # 4. Map the AI's generic citations (e.g., "chunk_0") back to the real DB records
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
            continue  # The AI hallucinated a chunk index that doesn't exist
            
    answer_obj.citations = hydrated_citations

    # 5. Extract the tokens so our FinOps middleware can charge for it!
    usage_dict = dict(response.usage) if response.usage else {}
    usage_dict["model"] = response.model
    
    return answer_obj, usage_dict
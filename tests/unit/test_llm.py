"""
tests/unit/test_llm.py

Tests for api/services/llm.py through the LiteLLM adapter (adapters/litellm_llm.py): prompt building, citation hydration, truncation
handling, retry on rate limit and cost accounting. litellm.acompletion is faked.

History: this file used to test classify_query_complexity(), which commit efde99f
removed on purpose (routing now picks one model). The old test was the stale side,
so it is rewritten against generate_with_citations / generate_with_routing.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from adapters.litellm_llm import LitellmLLM
from api.services.llm import (
    Citation,
    GeneratedAnswer,
    generate_with_citations,
    generate_with_routing,
)
from config import LLM_CONFIG, MODEL_PRICING

pytestmark = pytest.mark.unit

LLM = LitellmLLM(MODEL_PRICING)  # the real adapter, with the SDK call replaced in each test

CHUNKS = [
    {"document_id": "doc-a", "source_filename": "gdpr.md", "text": "GDPR fines reach 4 percent of turnover.", "score": 0.91},
    {"document_id": "doc-b", "source_filename": None, "text": "CCPA covers California residents.", "score": 0.55},
]


def _response(answer: GeneratedAnswer, finish_reason="stop", prompt=1000, completion=500):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(content=answer.model_dump_json()),
        )],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


def _answer(indexes):
    return GeneratedAnswer(
        answer="Fines are up to 4 percent.",
        confidence=0.8,
        citations=[
            Citation(document_id="x", chunk_index=i, relevance_score=0.0, excerpt="") for i in indexes
        ],
    )


async def test_citations_are_hydrated_from_real_chunks():
    fake = AsyncMock(return_value=_response(_answer([0, 1])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        answer, _ = await generate_with_citations(LLM, "What are GDPR fines?", CHUNKS)
    assert [c.document_id for c in answer.citations] == ["doc-a", "doc-b"]
    assert answer.citations[0].source_filename == "gdpr.md"
    assert answer.citations[1].source_filename == "unknown"
    assert answer.citations[0].relevance_score == 0.91
    assert answer.citations[0].excerpt == CHUNKS[0]["text"][:100]
    assert answer.answer == "Fines are up to 4 percent."
    assert answer.confidence == 0.8


async def test_hallucinated_chunk_index_is_dropped():
    fake = AsyncMock(return_value=_response(_answer([0, 7, -9])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        answer, _ = await generate_with_citations(LLM, "q", CHUNKS)
    # index 7 is out of range and is dropped. -9 is also out of range.
    assert [c.chunk_index for c in answer.citations] == [0]


async def test_prompt_contains_chunk_ids_filenames_and_question():
    fake = AsyncMock(return_value=_response(_answer([0])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        await generate_with_citations(LLM, "What are GDPR fines?", CHUNKS)
    prompt = fake.call_args.kwargs["messages"][0]["content"]
    assert "[chunk_0] (from gdpr.md, score 0.91)" in prompt
    assert "[chunk_1] (from unknown, score 0.55)" in prompt
    assert "Question: What are GDPR fines?" in prompt
    assert fake.call_args.kwargs["response_format"] is GeneratedAnswer
    assert fake.call_args.kwargs["max_tokens"] == 4000


async def test_default_model_comes_from_config_and_override_wins():
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await generate_with_citations(LLM, "q", CHUNKS)
        assert fake.call_args.kwargs["model"] == LLM_CONFIG["model"]
        assert usage["routed_model"] == LLM_CONFIG["model"]
        _, usage = await generate_with_citations(LLM, "q", CHUNKS, model="azure/gpt-4o")
        assert fake.call_args.kwargs["model"] == "azure/gpt-4o"
        assert usage["routed_model"] == "azure/gpt-4o"


async def test_usage_dict_carries_model_key_that_finops_reads():
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await generate_with_citations(LLM, "q", CHUNKS, model="azure/gpt-4o")
    assert usage["model"] == "azure/gpt-4o"  # regression B4: FinOps read "model", llm only set "routed_model"


async def test_cost_uses_model_pricing():
    fake = AsyncMock(return_value=_response(_answer([]), prompt=1_000_000, completion=1_000_000))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await generate_with_citations(LLM, "q", CHUNKS, model="azure/gpt-4o")
    assert usage["prompt_tokens"] == 1_000_000
    assert usage["completion_tokens"] == 1_000_000
    assert usage["total_cost"] == pytest.approx(2.50 + 10.00)


async def test_unknown_model_is_costed_at_the_highest_known_rate():  # Sprint 008 (QA M3): it used to cost 0
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await generate_with_citations(LLM, "q", CHUNKS, model="made-up/model")
    assert usage["total_cost"] > 0.0
    known = await _cost_of("azure/gpt-4o")
    assert usage["total_cost"] >= known  # never cheaper than a priced model with the same tokens


async def _cost_of(model: str) -> float:
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await generate_with_citations(LLM, "q", CHUNKS, model=model)
    return float(usage["total_cost"])


async def test_missing_usage_degrades_to_zero_tokens():
    resp = _response(_answer([]))
    resp.usage = None
    with patch("adapters.litellm_llm.litellm.acompletion", AsyncMock(return_value=resp)):
        _, usage = await generate_with_citations(LLM, "q", CHUNKS)
    assert (usage["prompt_tokens"], usage["completion_tokens"], usage["total_cost"]) == (0, 0, 0.0)


async def test_truncated_response_raises():
    fake = AsyncMock(return_value=_response(_answer([0]), finish_reason="length"))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        with pytest.raises(ValueError, match="truncated"):
            await generate_with_citations(LLM, "q", CHUNKS)


async def test_rate_limit_is_retried_then_succeeds():
    fake = AsyncMock(side_effect=[RuntimeError("rate_limit exceeded"), _response(_answer([0]))])
    sleep = AsyncMock()
    with patch("adapters.litellm_llm.litellm.acompletion", fake), patch("asyncio.sleep", sleep):
        answer, _ = await generate_with_citations(LLM, "q", CHUNKS)
    assert fake.call_count == 2
    sleep.assert_awaited_once_with(35)
    assert len(answer.citations) == 1


async def test_rate_limit_gives_up_after_three_attempts():
    fake = AsyncMock(side_effect=RuntimeError("Rate_Limit hit"))
    with patch("adapters.litellm_llm.litellm.acompletion", fake), patch("asyncio.sleep", AsyncMock()):
        with pytest.raises(RuntimeError, match="Rate_Limit"):
            await generate_with_citations(LLM, "q", CHUNKS)
    assert fake.call_count == 3


async def test_other_errors_are_not_retried():
    fake = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        with pytest.raises(RuntimeError, match="boom"):
            await generate_with_citations(LLM, "q", CHUNKS)
    assert fake.call_count == 1


async def test_empty_chunks_does_not_crash():
    fake = AsyncMock(return_value=_response(_answer([0])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        answer, _ = await generate_with_citations(LLM, "q", [])
    assert answer.citations == []


async def test_generate_with_routing_delegates_with_model():
    fake = AsyncMock(return_value=_response(_answer([0])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        answer, usage = await generate_with_routing(LLM, "q", CHUNKS, model="azure/gpt-4o")
    assert usage["routed_model"] == "azure/gpt-4o"
    assert json.loads(answer.model_dump_json())["citations"][0]["document_id"] == "doc-a"

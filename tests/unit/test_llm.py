"""
tests/unit/test_llm.py

Tests for api/services/llm.py through the LiteLLM adapter (adapters/litellm_llm.py): prompt building, citation hydration, truncation
handling, retry on rate limit and cost accounting. litellm.acompletion is faked.

History: this file used to test classify_query_complexity(), which commit efde99f
removed on purpose (routing now picks one model). The old test was the stale side,
so it is rewritten against generate_with_citations / generate_with_routing.
"""
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from adapters.litellm_llm import LitellmLLM
from api.services.llm import (
    Citation,
    GeneratedAnswer,
    generate_with_citations,
    generate_with_routing,
)
from api.services.model_calls import ModelCallFailed
from config import LLM_CONFIG, MODEL_PRICING
from tests.fakes import fake_resolved_model

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


async def test_legacy_ollama_completion_uses_configured_api_base(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:19001")
    llm = LitellmLLM(MODEL_PRICING, ollama_base_url="http://127.0.0.1:19002")
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        await llm.complete([{"role": "user", "content": "test"}], model="ollama/example", max_tokens=10)
    assert fake.call_args.kwargs["api_base"] == "http://127.0.0.1:19002"


async def test_legacy_ollama_env_alone_does_not_change_endpoint(monkeypatch):
    llm = LitellmLLM(MODEL_PRICING)
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:19001")
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        await llm.complete([{"role": "user", "content": "test"}], model="ollama_chat/example", max_tokens=10)
    assert fake.call_args.kwargs["api_base"] == "http://127.0.0.1:11434"


async def test_resolved_ollama_route_takes_precedence_and_other_providers_are_unchanged(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:19001")
    resolved = fake_resolved_model("ollama/example")
    resolved = replace(resolved, route=replace(resolved.route, endpoint="http://127.0.0.1:19002"))
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        await LLM.complete_resolved(resolved, [{"role": "user", "content": "test"}], max_tokens=10)
        assert fake.call_args.kwargs["api_base"] == "http://127.0.0.1:19002"
        await LLM.complete([{"role": "user", "content": "test"}], model="azure/gpt-4o", max_tokens=10)
        assert "api_base" not in fake.call_args.kwargs


async def _governed_call(generate, llm, query, chunks, model=None):
    import asyncio

    from api.services.model_calls import ModelCaller
    from core.settings import Settings
    from ports.models import ModelUse
    from tests.fakes import FakeCatalog, FakeModelLimitStore
    from tests.gateway_helpers import make_ctx

    alias = model or LLM_CONFIG["model"]
    resolved = fake_resolved_model(alias, ModelUse.COMPLETION)
    resolved = replace(resolved, price_ref=alias if alias in MODEL_PRICING else None)
    caller = ModelCaller(FakeCatalog({alias: resolved}), llm, FakeModelLimitStore(), settings=Settings(), sleep=asyncio.sleep)
    return await generate(llm, query, chunks, model=model, caller=caller, ctx=make_ctx())


async def _governed_citations(llm, query, chunks, model=None):
    return await _governed_call(generate_with_citations, llm, query, chunks, model)


async def _governed_routing(llm, query, chunks, model=None):
    return await _governed_call(generate_with_routing, llm, query, chunks, model)


async def test_citations_are_hydrated_from_real_chunks():
    fake = AsyncMock(return_value=_response(_answer([0, 1])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        answer, _ = await _governed_citations(LLM, "What are GDPR fines?", CHUNKS)
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
        answer, _ = await _governed_citations(LLM, "q", CHUNKS)
    # index 7 is out of range and is dropped. -9 is also out of range.
    assert [c.chunk_index for c in answer.citations] == [0]


async def test_prompt_contains_chunk_ids_filenames_and_question():
    fake = AsyncMock(return_value=_response(_answer([0])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        await _governed_citations(LLM, "What are GDPR fines?", CHUNKS)
    prompt = fake.call_args.kwargs["messages"][0]["content"]
    assert "[chunk_0] (from gdpr.md, score 0.91)" in prompt
    assert "[chunk_1] (from unknown, score 0.55)" in prompt
    assert "Question: What are GDPR fines?" in prompt
    assert fake.call_args.kwargs["response_format"] is GeneratedAnswer
    assert fake.call_args.kwargs["max_tokens"] == 4000


async def test_default_model_comes_from_config_and_override_wins():
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await _governed_citations(LLM, "q", CHUNKS)
        assert fake.call_args.kwargs["model"] == LLM_CONFIG["model"]
        assert usage["routed_model"] == LLM_CONFIG["model"]
        _, usage = await _governed_citations(LLM, "q", CHUNKS, model="azure/gpt-4o")
        assert fake.call_args.kwargs["model"] == "azure/gpt-4o"
        assert usage["routed_model"] == "azure/gpt-4o"


async def test_usage_dict_carries_model_key_that_finops_reads():
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await _governed_citations(LLM, "q", CHUNKS, model="azure/gpt-4o")
    assert usage["model"] == "azure/gpt-4o"  # regression B4: FinOps read "model", llm only set "routed_model"


async def test_cost_uses_model_pricing():
    fake = AsyncMock(return_value=_response(_answer([]), prompt=1_000_000, completion=1_000_000))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await _governed_citations(LLM, "q", CHUNKS, model="azure/gpt-4o")
    assert usage["prompt_tokens"] == 1_000_000
    assert usage["completion_tokens"] == 1_000_000
    assert usage["total_cost"] == pytest.approx(2.50 + 10.00)


async def test_unknown_model_is_costed_at_the_highest_known_rate():  # Sprint 008 (QA M3)
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        result = await LLM.complete([], model="made-up/model", max_tokens=10)
    assert result.cost_usd > 0.0
    known = await _cost_of("azure/gpt-4o")
    assert result.cost_usd >= known
    expected = (1000 * max(x["input"] for x in MODEL_PRICING.values()) +
                500 * max(x["output"] for x in MODEL_PRICING.values())) / 1_000_000
    assert result.cost_usd == pytest.approx(expected)


async def test_governed_unknown_alias_is_denied():
    from api.services.model_calls import ModelCaller
    from core.settings import Settings
    from gateway import GatewayDenied
    from ports.llm import Completion
    from tests.fakes import FakeCatalog, FakeModelLimitStore
    from tests.gateway_helpers import make_ctx

    provider = AsyncMock()
    provider.complete_resolved.return_value = Completion(text=_answer([]).model_dump_json(), model="made-up/model", tokens_in=1, tokens_out=1, cost_usd=0.0, finish_reason="stop")
    caller = ModelCaller(FakeCatalog(), provider, FakeModelLimitStore(), settings=Settings())
    with pytest.raises(GatewayDenied) as denied:
        await generate_with_citations(provider, "q", CHUNKS, model="made-up/model", caller=caller, ctx=make_ctx())
    assert denied.value.decision.reason == "model_unknown"
    provider.complete_resolved.assert_not_awaited()


async def _cost_of(model: str) -> float:
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        _, usage = await _governed_citations(LLM, "q", CHUNKS, model=model)
    return float(usage["total_cost"])


async def test_missing_usage_degrades_to_zero_tokens():
    resp = _response(_answer([]))
    resp.usage = None
    with patch("adapters.litellm_llm.litellm.acompletion", AsyncMock(return_value=resp)):
        _, usage = await _governed_citations(LLM, "q", CHUNKS)
    assert (usage["prompt_tokens"], usage["completion_tokens"], usage["total_cost"]) == (0, 0, 0.0)


async def test_truncated_response_raises():
    fake = AsyncMock(return_value=_response(_answer([0]), finish_reason="length"))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        with pytest.raises(ValueError, match="truncated"):
            await _governed_citations(LLM, "q", CHUNKS)


async def test_rate_limit_is_retried_then_succeeds():
    fake = AsyncMock(side_effect=[litellm.RateLimitError("rate limit", llm_provider="ollama", model="test"), _response(_answer([0]))])
    sleep = AsyncMock()
    with patch("adapters.litellm_llm.litellm.acompletion", fake), patch("asyncio.sleep", sleep):
        answer, _ = await _governed_citations(LLM, "q", CHUNKS)
    assert fake.call_count == 2
    sleep.assert_awaited_once_with(0.25)
    assert len(answer.citations) == 1


async def test_rate_limit_gives_up_after_three_attempts():
    fake = AsyncMock(side_effect=litellm.RateLimitError("rate limit", llm_provider="ollama", model="test"))
    with patch("adapters.litellm_llm.litellm.acompletion", fake), patch("asyncio.sleep", AsyncMock()):
        with pytest.raises(ModelCallFailed, match="rate_limited"):
            await _governed_citations(LLM, "q", CHUNKS)
    assert fake.call_count == 3


async def test_other_errors_are_not_retried():
    fake = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        with pytest.raises(ModelCallFailed, match="provider_error"):
            await _governed_citations(LLM, "q", CHUNKS)
    assert fake.call_count == 1


async def test_empty_chunks_does_not_crash():
    fake = AsyncMock(return_value=_response(_answer([0])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        answer, _ = await _governed_citations(LLM, "q", [])
    assert answer.citations == []


async def test_generate_with_routing_delegates_with_model():
    fake = AsyncMock(return_value=_response(_answer([0])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        answer, usage = await _governed_routing(LLM, "q", CHUNKS, model="azure/gpt-4o")
    assert usage["routed_model"] == "azure/gpt-4o"
    assert json.loads(answer.model_dump_json())["citations"][0]["document_id"] == "doc-a"

async def test_registry_injects_same_endpoint_into_legacy_llm_and_catalog(monkeypatch, tmp_path):
    from adapters.registry import build_adapters
    from core.settings import Settings

    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:19001")
    settings = Settings(mode="local", ollama_base_url="http://127.0.0.1:19002", object_store_dir=str(tmp_path))
    bundle = build_adapters(settings, pool=object())
    fake = AsyncMock(return_value=_response(_answer([])))
    with patch("adapters.litellm_llm.litellm.acompletion", fake):
        await bundle.llm.complete([{"role": "user", "content": "test"}], model="ollama/example", max_tokens=10)
    assert fake.call_args.kwargs["api_base"] == "http://127.0.0.1:19002"
    assert bundle.model_catalog.local.endpoint == "http://127.0.0.1:19002"

@pytest.mark.parametrize("endpoint", ["", "file:///tmp/socket", "http://"])
def test_ollama_endpoint_is_validated_at_startup(endpoint):
    from core.settings import Settings

    with pytest.raises(ValueError, match="ollama_base_url"):
        Settings(mode="local", ollama_base_url=endpoint)


@pytest.mark.parametrize("generate", [generate_with_citations, generate_with_routing])
@pytest.mark.parametrize("kwargs", [{}, {"caller": None, "ctx": object()}])
async def test_missing_governed_caller_fails_closed(generate, kwargs):
    provider = AsyncMock()
    with pytest.raises((TypeError, ValueError)):
        await generate(provider, "q", CHUNKS, **kwargs)
    provider.complete.assert_not_awaited()


@pytest.mark.parametrize("generate", [generate_with_citations, generate_with_routing])
@pytest.mark.parametrize("kwargs", [{}, {"ctx": None}])
async def test_missing_governance_context_fails_closed(generate, kwargs):
    provider, caller = AsyncMock(), AsyncMock()
    with pytest.raises((TypeError, ValueError)):
        await generate(provider, "q", CHUNKS, caller=caller, **kwargs)
    caller.complete.assert_not_awaited()
    provider.complete.assert_not_awaited()

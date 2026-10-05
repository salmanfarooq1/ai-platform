"""One contract for every `LLMPort` and `ChatModelPort`: the fake, and the LiteLLM adapters with the SDK call replaced.

The LiteLLM adapters are also run with the SDK left alone: the network guard must make them raise cleanly.
"""
import json

import litellm
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from adapters.litellm_chat import LitellmChat
from adapters.litellm_llm import LitellmLLM
from config import MODEL_PRICING
from ports import Completion
from tests.fakes import FakeLLM, NetworkBlockedError

MODEL = "gemini/gemini-3.5-flash-lite"
PROMPT = "Context Chunks:\n\n[chunk_0] (from gdpr.md, score 0.50):\nBreach notification takes 72 hours.\n\nQuestion: how long?\n"


class Answer(BaseModel):
    answer: str
    confidence: float
    citations: list[dict]


@pytest.fixture(params=["fake", "litellm-adapter"])
def llm(request, monkeypatch):
    fake = FakeLLM()
    if request.param == "fake":
        return fake
    monkeypatch.setattr(litellm, "acompletion", fake.acompletion)  # the SDK call, replaced: the adapter is real
    return LitellmLLM(MODEL_PRICING)


@pytest.fixture(params=["fake", "litellm-adapter"])
def chat(request, monkeypatch):
    fake = FakeLLM(agent_namespace="legal")
    if request.param == "fake":
        return fake
    monkeypatch.setattr(litellm, "acompletion", fake.acompletion)
    return LitellmChat(MODEL)


async def test_complete_returns_a_typed_completion(llm):
    result = await llm.complete([{"role": "user", "content": PROMPT}], model=MODEL, max_tokens=100, response_format=Answer)
    assert isinstance(result, Completion)
    assert result.model == MODEL and result.finish_reason == "stop"
    assert isinstance(result.tokens_in, int) and result.tokens_in > 0 and result.tokens_out == 7
    assert result.cost_usd == 0.0  # the free-tier model costs nothing in the price table
    body = json.loads(result.text)
    assert body["citations"][0]["chunk_index"] == 0 and "72 hours" in body["answer"]


async def test_complete_prices_a_paid_model_from_the_price_table(llm):
    result = await llm.complete([{"role": "user", "content": PROMPT}], model="azure/gpt-4o", max_tokens=100)
    rates = MODEL_PRICING["azure/gpt-4o"]
    expected = (result.tokens_in / 1e6) * rates["input"] + (result.tokens_out / 1e6) * rates["output"]
    assert result.cost_usd == pytest.approx(expected) and result.cost_usd > 0


async def test_complete_accepts_a_temperature_and_no_response_format(llm):
    result = await llm.complete([{"role": "user", "content": "hello"}], model=MODEL, max_tokens=10, temperature=0.0)
    assert result.text == "ok"


@tool
async def retrieve_chunks(query: str, namespace: str = "default") -> str:
    """Fake retrieve tool."""
    return "{}"


async def test_a_bound_chat_model_returns_tool_calls_then_text(chat):
    model = chat.chat_model(max_tokens=50).bind_tools([retrieve_chunks])
    first = await model.ainvoke([SystemMessage(content="You research."), HumanMessage(content="What is the deadline?")])
    assert isinstance(first, AIMessage)
    assert [(c["name"], c["args"]["namespace"]) for c in first.tool_calls] == [("retrieve_chunks", "legal")]

    second = await model.ainvoke([
        SystemMessage(content="You research."), HumanMessage(content="What is the deadline?"), first,
        ToolMessage(content="{}", tool_call_id=first.tool_calls[0]["id"]),
    ])
    assert second.tool_calls == [] and second.content == "Enough context retrieved."


async def test_the_chat_port_prices_a_call_or_raises(chat):
    """`cost` is best effort: a number, or an exception the caller swallows (the agent graph does)."""
    try:
        cost = chat.cost("azure/gpt-4o", 1000, 500)
    except Exception:
        return
    assert isinstance(cost, float) and cost >= 0.0


async def test_a_provider_failure_surfaces_as_an_exception(monkeypatch):
    async def down(**kwargs):
        raise ConnectionError("provider down")

    monkeypatch.setattr(litellm, "acompletion", down)
    for port in (LitellmLLM(MODEL_PRICING),):
        with pytest.raises(ConnectionError):
            await port.complete([{"role": "user", "content": "x"}], model=MODEL, max_tokens=5)

    class Failing(FakeLLM):
        async def acompletion(self, **kwargs):
            raise ConnectionError("provider down")

    failing = FakeLLM()
    failing.use(Failing())
    with pytest.raises(ConnectionError):
        await failing.complete([{"role": "user", "content": "x"}], model=MODEL, max_tokens=5)


async def test_the_litellm_adapters_under_the_network_guard_raise_cleanly():
    """No fake installed: the guard replaces litellm's entry points, so the adapter raises NetworkBlockedError."""
    with pytest.raises(NetworkBlockedError, match="litellm.acompletion"):
        await LitellmLLM(MODEL_PRICING).complete([{"role": "user", "content": "x"}], model=MODEL, max_tokens=5)
    with pytest.raises(NetworkBlockedError):
        await LitellmChat(MODEL).chat_model(max_tokens=5).ainvoke([HumanMessage(content="x")])

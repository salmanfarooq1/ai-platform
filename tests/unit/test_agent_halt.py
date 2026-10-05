"""After a denial ends an agent run (`ctx.halted`), the graph spends no more model calls: not on the agent, not on the verifier."""
import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

import api.agent.graph as graph_module
from api.agent.models import AGENT_MAX_TOKENS, VERIFIER_MAX_TOKENS
from api.services.llm import GENERATION_MAX_TOKENS
from gateway import Action, ActionKind, enforce
from gateway.estimate import estimate_tokens
from tests.gateway_helpers import make_ctx


class CountingModel:
    def __init__(self, reply: str, calls: list[str], name: str):
        self.reply, self.calls, self.name = reply, calls, name

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls.append(self.name)
        return AIMessage(content=self.reply)


@tool
async def fake_retrieve(query: str, namespace: str = "default") -> str:
    """Fake retrieve tool."""
    return json.dumps({"chunks": [{"document_id": "doc1", "chunk_index": 0, "content": "text"}]})


class CountingChat:
    """A `ChatModelPort` whose models count their calls."""

    def __init__(self, calls: list[str]):
        self.calls = calls

    def chat_model(self, *, max_tokens, temperature=0.0):
        if max_tokens == AGENT_MAX_TOKENS:
            return CountingModel("done", self.calls, "agent")
        return CountingModel(json.dumps({"supported": True, "notes": "ok"}), self.calls, "verifier")

    def cost(self, model, tokens_in, tokens_out):
        return 0.0


def build(monkeypatch, calls):
    monkeypatch.setattr(graph_module, "make_retrieve_tool", lambda adapters: fake_retrieve)
    return graph_module.build_agent_graph(SimpleNamespace(chat=CountingChat(calls), llm=None, knowledge=None, embeddings=None))


def state(verifier=True):
    return {"messages": [HumanMessage(content="question")], "reasoning_usage": [], "verifier_usage": [],
            "synthesis_usage": [], "enable_verifier": verifier, "verify_retries_left": 1}


async def test_a_halted_run_makes_no_agent_call_and_no_verifier_call(monkeypatch, gateway_io):
    calls: list[str] = []
    ctx = make_ctx()
    ctx.halted = "tool_call_limit"
    result = await build(monkeypatch, calls).ainvoke(state(), config={"recursion_limit": 10, "configurable": {"gateway": ctx}})
    assert calls == []
    assert "tool_call_limit" in result["verification_notes"]
    assert result["verifier_usage"] == []
    assert gateway_io.decisions == []  # and no model.invoke decision was even asked for


async def test_a_run_that_is_not_halted_still_verifies(monkeypatch, gateway_io):
    calls: list[str] = []
    result = await build(monkeypatch, calls).ainvoke(
        state(), config={"recursion_limit": 10, "configurable": {"gateway": make_ctx()}})
    assert calls == ["agent", "verifier"]  # nothing halted the run, so the verifier is gated, allowed and called
    assert result["verified"] is True


async def test_a_verifier_denied_by_policy_halts_without_a_call(monkeypatch, gateway_io):
    calls: list[str] = []
    ctx = make_ctx(policy={"allowed_models": "*", "allowed_tools": "*", "allowed_kbs": "*", "max_tokens_per_request": VERIFIER_MAX_TOKENS})
    result = await build(monkeypatch, calls).ainvoke(state(), config={"recursion_limit": 10, "configurable": {"gateway": ctx}})
    assert "verifier" not in calls
    assert ctx.halted == "token_limit"
    assert "not permitted" in result["verification_notes"] or "cut short" in result["verification_notes"]


def test_the_model_estimates_include_the_completion_tokens_they_ask_for():
    assert estimate_tokens("", GENERATION_MAX_TOKENS) == 1 + GENERATION_MAX_TOKENS
    assert estimate_tokens("a" * 400) == 101
    msgs = [HumanMessage(content="a" * 400)]
    assert graph_module._estimate_tokens(msgs, AGENT_MAX_TOKENS) == 101 + AGENT_MAX_TOKENS


async def test_enforce_denies_a_model_call_whose_completion_tokens_push_it_over_the_cap():
    ctx = make_ctx(policy={"allowed_models": "*", "allowed_tools": "*", "allowed_kbs": "*", "max_tokens_per_request": GENERATION_MAX_TOKENS})
    fits_without = Action(ActionKind.MODEL_INVOKE, "m", estimated_tokens=estimate_tokens("short question"))
    over_with = Action(ActionKind.MODEL_INVOKE, "m", estimated_tokens=estimate_tokens("short question", GENERATION_MAX_TOKENS))
    assert (await enforce(ctx, fits_without)).allowed
    decision = await enforce(ctx, over_with)
    assert (decision.allowed, decision.stage, decision.reason) == (False, "policy", "token_limit")

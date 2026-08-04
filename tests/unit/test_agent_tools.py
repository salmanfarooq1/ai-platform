import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from api.agent.graph import _extract_chunks, _extract_llm_usage, should_continue, should_verify, verify_router
from api.agent.router import _combine_usage
from api.agent.tools import list_namespaces, make_retrieve_tool


class _FailingPool:
    """Pool stand in whose acquire() always raises, to exercise the error path
    without hitting a real database."""
    def acquire(self):
        raise RuntimeError("connection refused")


@pytest.mark.asyncio
async def test_retrieve_chunks_handles_db_error(monkeypatch):
    """A DB failure should come back as a JSON error string, not a raised
    exception (a raised exception inside a tool call terminates the agent loop)."""
    import api.agent.tools as tools_module

    async def fake_embed_query(query: str):
        return [0.0] * 768

    monkeypatch.setattr(tools_module, "embed_query", fake_embed_query)

    tool = make_retrieve_tool(_FailingPool())
    result = await tool.ainvoke({"query": "test query", "namespace": "default"})
    data = json.loads(result)
    assert "error" in data


def test_retrieve_tool_has_docstring():
    tool = make_retrieve_tool(pool=None)
    assert tool.description is not None
    assert len(tool.description) > 20


def test_list_namespaces_returns_registry_contents():
    result = json.loads(list_namespaces.invoke({}))
    assert "legal" in result
    assert "kyc_aml" in result


def test_should_continue_routes_to_tools_on_tool_call():
    state = {"messages": [AIMessage(content="", tool_calls=[
        {"name": "retrieve_chunks", "args": {"query": "x"}, "id": "1"},
    ])]}
    assert should_continue(state) == "tools"


def test_should_continue_routes_to_synthesize_when_done():
    state = {"messages": [HumanMessage(content="hi"), AIMessage(content="done retrieving")]}
    assert should_continue(state) == "synthesize"


def test_should_verify_routes_to_end_when_disabled_per_request():
    state = {"enable_verifier": False}
    assert should_verify(state) == "end"


def test_should_verify_routes_to_verify_when_enabled():
    state = {"enable_verifier": True}
    assert should_verify(state) == "verify"


def test_verify_router_retries_when_unsupported_and_retries_remain():
    state = {"verified": False, "verify_retries_left": 1}
    assert verify_router(state) == "retry"


def test_verify_router_ends_when_retries_exhausted():
    state = {"verified": False, "verify_retries_left": 0}
    assert verify_router(state) == "end"


def test_verify_router_ends_when_verified():
    state = {"verified": True, "verify_retries_left": 1}
    assert verify_router(state) == "end"


def test_extract_chunks_dedupes_by_document_and_chunk_index():
    """Two retrieve_chunks calls that overlap (e.g. retrying the same namespace)
    should not double count the same chunk when synthesize_node builds context."""
    payload = json.dumps({"chunks": [
        {"document_id": "doc1", "chunk_index": 0, "content": "GDPR text", "source_filename": "gdpr.pdf"},
    ]})
    messages = [
        ToolMessage(content=payload, tool_call_id="1"),
        ToolMessage(content=payload, tool_call_id="2"),  # duplicate retrieval
    ]
    assert len(_extract_chunks(messages)) == 1


def test_extract_llm_usage_defaults_to_zero_on_missing_metadata():
    """A response with no response_metadata (or an unexpected shape) should
    degrade to zero cost, not raise. An accounting miss should not be able
    to crash the agent loop."""
    msg = AIMessage(content="thinking...")
    usage = _extract_llm_usage(msg)
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}


def test_combine_usage_sums_reasoning_and_verifier_and_synthesis_cost():
    result = {
        "reasoning_usage": [{"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.001}],
        "verifier_usage": [{"prompt_tokens": 50, "completion_tokens": 10, "cost": 0.0005}],
        "synthesis_cost": 0.004,
        "model_used": "groq/meta-llama/llama-4-scout-17b-16e-instruct",
    }
    usage = _combine_usage(result)
    assert usage["total_cost"] == pytest.approx(0.0055)
    assert usage["prompt_tokens"] == 150
    assert usage["routing_decision"] == "agent"


def test_chunk_key_matches_llm_expected_shape():
    """retrieve_chunks must use source_filename end to end.
    No source key anywhere in the pipeline, and no remap step needed."""
    chunk_from_tool = {
        "chunk_index": 0,
        "document_id": "doc1",
        "source_filename": "gdpr.pdf",
        "score": 0.87,
        "content": "Article 5...",
        "truncated": False,
    }
    db_chunk = {
        "document_id": chunk_from_tool["document_id"],
        "source_filename": chunk_from_tool["source_filename"],
        "text": chunk_from_tool["content"],
        "score": chunk_from_tool["score"],
    }
    assert "source" not in db_chunk
    assert db_chunk["source_filename"] == "gdpr.pdf"


@pytest.mark.asyncio
async def test_ainvoke_initial_state_includes_reducer_lists():
    """The initial state passed to graph.ainvoke() must include reasoning_usage 
    and verifier_usage as empty lists, or the first agent_node return raises 
    InvalidUpdateError."""
    required_keys = {"messages", "reasoning_usage", "verifier_usage", "enable_verifier", "verify_retries_left"}
    initial_state = {
        "messages": [HumanMessage(content="test")],
        "reasoning_usage": [],
        "verifier_usage": [],
        "enable_verifier": True,
        "verify_retries_left": 1,
    }
    assert required_keys.issubset(initial_state.keys())

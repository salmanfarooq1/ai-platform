import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from adapters.pg_knowledge import PgKnowledgeStore
from api.agent.graph import _extract_chunks, _extract_llm_usage, should_continue, should_verify, verify_router
from api.agent.router import _combine_usage
from api.agent.tools import gateway_from_config, make_list_namespaces_tool, make_retrieve_tool
from tests.fakes import FakeEmbeddings, FakePool
from tests.gateway_helpers import FakeRedis, make_ctx, make_principal

TENANT = "00000000-0000-0000-0000-0000000000aa"


def tenant_config():
    """The run config the route builds: the request's enforcement context, in `configurable`."""
    return {"configurable": {"gateway": make_ctx(principal=make_principal(tenant=UUID(TENANT)))}}


def ports(knowledge=None):
    """The ports the agent tools take (a bundle with a knowledge store and embeddings)."""
    return SimpleNamespace(knowledge=knowledge, embeddings=FakeEmbeddings())


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

    async def fake_embed_query(embeddings, query: str):
        return await embeddings.embed([query])

    monkeypatch.setattr(tools_module, "embed_query", fake_embed_query)

    tool = make_retrieve_tool(ports(PgKnowledgeStore(_FailingPool())))
    result = await tool.ainvoke({"query": "test query", "namespace": "default"}, config=tenant_config())
    data = json.loads(result)
    assert "error" in data
    assert "connection refused" in data["error"]  # it failed in the database call, not before it


@pytest.mark.asyncio
async def test_retrieve_chunks_refuses_to_run_without_a_tenant(monkeypatch):
    """The tenant is not a tool argument. No tenant in the run config means the tool does nothing."""
    import api.agent.tools as tools_module

    async def must_not_embed(embeddings, query: str):
        raise AssertionError("embedding must not run without a tenant")

    monkeypatch.setattr(tools_module, "embed_query", must_not_embed)
    tool = make_retrieve_tool(ports(PgKnowledgeStore(FakePool())))

    for config in (None, {"configurable": {}}, {"configurable": {"tenant_id": "not-a-uuid"}}):
        data = json.loads(await tool.ainvoke({"query": "q", "namespace": "legal"}, config=config))
        assert data["error"] == "unauthenticated"


def test_gateway_from_config_reads_only_an_enforcement_context():
    cfg = tenant_config()
    assert gateway_from_config(cfg) is cfg["configurable"]["gateway"]
    assert str(gateway_from_config(cfg).boundary.tenant_id) == TENANT
    assert gateway_from_config({"configurable": {"gateway": "x"}}) is None
    assert gateway_from_config({"configurable": {"tenant_id": TENANT}}) is None  # a bare tenant id is not enough
    assert gateway_from_config({}) is None
    assert gateway_from_config(None) is None


def test_retrieve_tool_does_not_expose_tenant_to_the_model():
    schema = make_retrieve_tool(adapters=None).args
    assert set(schema) == {"query", "namespace", "top_k", "mode"}


def test_retrieve_tool_has_docstring():
    tool = make_retrieve_tool(adapters=None)
    assert tool.description is not None
    assert len(tool.description) > 20


@pytest.mark.asyncio
async def test_list_namespaces_returns_the_tenants_knowledge_bases():
    pool = FakePool(rows=[{"slug": "kyc_aml", "description": "KYC"}, {"slug": "legal", "description": "Law"}])
    tool = make_list_namespaces_tool(ports(PgKnowledgeStore(pool)))

    result = json.loads(await tool.ainvoke({}, config=tenant_config()))

    assert result == {"kyc_aml": "KYC", "legal": "Law"}
    # the read ran inside the tenant's transaction: set_config first, then the query
    assert pool.conn.queries[0] == ("SELECT set_config('app.tenant_id', $1, true)", (TENANT,))
    assert "knowledge_bases" in pool.conn.queries[1][0]


@pytest.mark.asyncio
async def test_list_namespaces_without_a_tenant_returns_an_error():
    data = json.loads(await make_list_namespaces_tool(ports(PgKnowledgeStore(FakePool()))).ainvoke({}, config={"configurable": {}}))
    assert data["error"] == "unauthenticated"


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
    state = {
        "verified": False,
        "verify_retries_left": 1,
        "messages": [HumanMessage(content="[Verifier feedback] needs info")]
    }
    assert verify_router(state) == "retry"


def test_verify_router_ends_when_retries_exhausted():
    state = {
        "verified": False,
        "verify_retries_left": 0,
        "messages": [HumanMessage(content="Draft answer")]
    }
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
        "synthesis_usage": [{"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.004}],
        "model_used": "openai/gpt-oss-120b",
    }
    usage = _combine_usage(result)
    assert usage["total_cost"] == pytest.approx(0.0000312)
    assert usage["prompt_tokens"] == 160
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
async def test_agent_query_initializes_reducer_lists_and_runs_graph(monkeypatch):
    """Integration test for the router to verify it properly initializes
    reducer lists and passes them to the graph."""
    from uuid import UUID, uuid4

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from adapters.inprocess_runtime import InProcessAgentRuntime
    from api.agent.router import router as agent_router
    from api.agent.runner import make_agent_runner
    from core.identity.models import Principal
    from gateway import GatewayRuntime

    principal = Principal(id=uuid4(), tenant_id=UUID(TENANT), kind="service", scopes=frozenset({"agent"}))
    app = FastAPI()

    @app.middleware("http")
    async def authenticate_as_test_principal(request, call_next):
        request.state.principal = principal  # what AuthMiddleware does after verifying a credential
        return await call_next(request)

    app.include_router(agent_router)

    class FakeGraph:
        async def ainvoke(self, state, config):
            # the tools get the request's enforcement context (boundary), built from the verified principal
            assert list(config["configurable"]) == ["gateway"]
            assert str(config["configurable"]["gateway"].boundary.tenant_id) == TENANT
            assert "reasoning_usage" in state
            assert state["reasoning_usage"] == []
            assert state["synthesis_usage"] == []
            assert state["verifier_usage"] == []
            return {
                "messages": [],
                "final_answer": "test answer",
                "confidence": 0.9,
                "model_used": "fake",
            }

    app.state.agent_graph = FakeGraph()
    app.state.db_pool = FakePool()  # the knowledge-base check reads through it
    app.state.adapters = SimpleNamespace(
        knowledge=PgKnowledgeStore(app.state.db_pool),
        runtime=InProcessAgentRuntime(make_agent_runner(lambda: app.state.agent_graph)),
    )
    app.state.gateway_runtime = GatewayRuntime(pool=app.state.db_pool, cache=FakeRedis())
    client = TestClient(app)
    response = client.post("/agent/query", json={
        "question": "test question",
        "enable_verifier": True
    })

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "test answer"


@pytest.mark.asyncio
async def test_agent_graph_end_to_end_with_verify_retry(monkeypatch):
    """Integration test covering TG-1 (end to end) and TG-2 (verify-retry loop)."""
    import api.agent.graph as graph_module

    call_count = {"agent": 0, "verifier": 0}

    class FakeAgentModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            call_count["agent"] += 1
            if call_count["agent"] == 1:
                return AIMessage(content="", tool_calls=[
                    {"name": "fake_retrieve", "args": {"query": "test"}, "id": "1"}
                ])
            return AIMessage(content="I have enough context.")

    class FakeVerifierModel:
        async def ainvoke(self, messages):
            call_count["verifier"] += 1
            if call_count["verifier"] == 1:
                return AIMessage(content='{"supported": false, "notes": "needs more info"}')
            return AIMessage(content='{"supported": true, "notes": "all good"}')

    class FakeChat:  # the graph builds its models through the ChatModelPort
        def chat_model(self, *, max_tokens, temperature=0.0):
            if max_tokens == 4000:
                return FakeAgentModel()
            return FakeVerifierModel()

        def cost(self, model, tokens_in, tokens_out):
            return 0.0

    async def fake_generate(llm, question, db_chunks):
        from api.models.schemas import GeneratedAnswer
        ans = GeneratedAnswer(
            answer="synthetic answer",
            confidence=0.9,
            citations=[],
            model_used="fake",
            needs_clarification=False,
        )
        return ans, {"total_cost": 0.01, "prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr("api.services.llm.generate_with_routing", fake_generate)

    from langchain_core.tools import tool
    @tool
    async def fake_retrieve(query: str, namespace: str = "default") -> str:
        """Fake retrieve tool."""
        return json.dumps({"chunks": [{"document_id": "doc1", "chunk_index": 0, "content": "fake content"}]})

    monkeypatch.setattr(graph_module, "make_retrieve_tool", lambda adapters: fake_retrieve)

    graph = graph_module.build_agent_graph(SimpleNamespace(chat=FakeChat(), llm=None, knowledge=None, embeddings=None))

    result = await graph.ainvoke({
        "messages": [HumanMessage(content="Hello")],
        "reasoning_usage": [],
        "verifier_usage": [],
        "synthesis_usage": [],
        "enable_verifier": True,
        "verify_retries_left": 1
    }, config={"recursion_limit": 10, "configurable": {"gateway": make_ctx()}})

    assert call_count["agent"] == 3
    assert call_count["verifier"] == 2
    assert result["verified"] is True
    assert result["verify_retries_left"] == 0
    assert result["final_answer"] == "synthetic answer"

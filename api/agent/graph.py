import json
import logging
from collections.abc import Callable
from operator import add
from typing import Annotated, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from api.agent.models import AGENT_MAX_TOKENS, VERIFIER_MAX_TOKENS
from api.agent.tools import gateway_from_config, make_list_namespaces_tool, make_retrieve_tool
from config import FEATURES, LLM_CONFIG
from gateway import Action, ActionKind, EnforcementContext, enforce, estimate_tokens
from ports import Adapters

logger = logging.getLogger("api.agent.graph")

SYNTHESIS_MAX_TOKENS = 4000  # api/services/llm.py asks for this many completion tokens


class AgentState(TypedDict):
    """
    State flowing through every node.

    messages accumulates via add_messages (append, not replace).
    reasoning_usage / verifier_usage accumulate via plain list
    concatenation (add) (one entry per LLM call in that role). Both MUST
    be initialized as empty lists wherever ainvoke() is first called
    (Task 7). Without that initialization, LangGraph raises InvalidUpdateError
    the first time agent_node tries to append to a key that was never in state.

    final_answer / confidence / citations / model_used / tokens_used /
    synthesis_cost are set once, by synthesize_node. enable_verifier and
    verify_retries_left come from the request. verified /
    verification_notes are set once, by verify_node, and stay unset if
    verification never ran.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    reasoning_usage: Annotated[list[dict], add]
    verifier_usage: Annotated[list[dict], add]
    final_answer: str
    confidence: float
    citations: list[dict]
    model_used: str
    synthesis_usage: Annotated[list[dict], add]
    enable_verifier: bool
    verify_retries_left: int
    verified: bool
    verification_notes: str


AGENT_SYSTEM_PROMPT = """You are an expert compliance research assistant with access to a regulatory document database.

You have two tools:
* list_namespaces: discover which document namespaces exist and what each contains
* retrieve_chunks: search a namespace for relevant regulatory text

For every question:
1. If you are unsure which namespace fits the question, call list_namespaces rather than guessing.
2. Use retrieve_chunks to find relevant documents. If the question involves comparing regulations across different namespaces, retrieve from EACH namespace separately.
3. Once you have sufficient context, stop calling tools (a final answer will be generated automatically from what you retrieved).
4. If you cannot find relevant documents after a reasonable search, stop anyway and say so; do not keep retrying indefinitely.
5. If you see a "[Verifier feedback]" message in the conversation, it means a previous draft had an unsupported claim. Retrieve whatever additional context would address it before stopping again.

Be thorough about retrieval. You do not write the final answer yourself, just gather the right context."""


VERIFIER_SYSTEM_PROMPT = """You are a compliance answer verifier. You will be shown a draft answer and the source chunks it was built from.

Check whether every factual claim in the draft is supported by the provided chunks. Minor gaps or partial coverage are fine, only flag it if there is a clear, material claim with no grounding in the chunks shown.

Respond with only a JSON object, nothing else:
{"supported": true or false, "notes": "brief explanation, or the specific unsupported claim"}"""


def _extract_chunks(messages: list[BaseMessage]) -> list[dict]:
    """Pull every chunk surfaced by retrieve_chunks calls, deduped by (document_id, chunk_index)."""
    seen = set()
    chunks = []
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        try:
            data = json.loads(str(m.content))  # list-shaped content is not JSON and is skipped below
        except (json.JSONDecodeError, TypeError):
            continue
        for c in data.get("chunks", []):
            key = (c.get("document_id"), c.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            chunks.append(c)
    return chunks


def _extract_llm_usage(response: BaseMessage, cost_of: Callable[[str, int, int], float] | None = None) -> dict:
    """
    Pull token counts (and cost, if computable) off a single ChatLiteLLM
    response, used for both the reasoning role and the verifier role, so
    every LLM call in the graph contributes to cost tracking, not just the
    final synthesis step.
    """
    meta = getattr(response, "response_metadata", {}) or {}
    usage = meta.get("token_usage", {}) or meta.get("usage", {}) or {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    cost = 0.0
    if cost_of is not None:
        try:
            cost = cost_of(meta.get("model", LLM_CONFIG["model"]), prompt_tokens, completion_tokens)
        except Exception:
            pass  # cost is best effort; token counts are the part we rely on

    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost": cost}


def _estimate_tokens(messages: list[BaseMessage], max_completion_tokens: int) -> int:
    """Input size plus the completion tokens this call asks for, for the policy's per-request token cap."""
    return estimate_tokens("".join(str(m.content) for m in messages), max_completion_tokens)


async def _model_allowed(config: RunnableConfig | None, texts: str, estimated_tokens: int) -> bool:
    """`enforce(model.invoke)` for one LLM call of this run. A deny ends the loop (`ctx.halted`)."""
    ctx: EnforcementContext | None = gateway_from_config(config)
    if ctx is None:
        return False  # no gateway context: fail closed
    decision = await enforce(ctx, Action(
        ActionKind.MODEL_INVOKE, LLM_CONFIG["model"], estimated_tokens=estimated_tokens, input_text=texts,
    ))
    if not decision.allowed:
        ctx.halted = decision.reason
    return decision.allowed


def make_synthesize_node(adapters: Adapters):
    async def node(state: AgentState, config: RunnableConfig | None = None) -> dict:
        return await synthesize_node(state, config, adapters)

    return node


async def synthesize_node(state: AgentState, config: RunnableConfig | None, adapters: Adapters) -> dict:
    """
    Deterministic finalizer. Always runs once the agent stops requesting
    tools. Not an LLM tool call, so there is no path where a query returns
    an answer without citations, a confidence score, and usage tracking.
    """
    from api.services.llm import generate_with_routing  # imported here so tests can replace the module attribute

    question = str(next(
        (m.content for m in state["messages"] if isinstance(m, HumanMessage)),
        "",
    ))
    chunks = _extract_chunks(state["messages"])

    if not chunks:
        return {
            "final_answer": "I could not find relevant documents to answer this question.",
            "confidence": 0.0,
            "citations": [],
            "model_used": "",
            "synthesis_usage": [{"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}],
        }

    db_chunks = [
        {
            "document_id": c["document_id"],
            "source_filename": c.get("source_filename") or "unknown",
            "text": c["content"],
            "score": c.get("score", 0.0),
        }
        for c in chunks
    ]

    if not await _model_allowed(config, question, estimate_tokens(question, SYNTHESIS_MAX_TOKENS)):
        return {
            "final_answer": "I could not generate an answer: the model call is not permitted within your limits.",
            "confidence": 0.0,
            "citations": [],
            "model_used": "",
            "synthesis_usage": [{"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}],
        }

    answer_obj, usage_dict = await generate_with_routing(adapters.llm, question, db_chunks)

    return {
        "final_answer": answer_obj.answer,
        "confidence": answer_obj.confidence,
        "citations": [
            {
                "document_id": c.document_id,
                "source_filename": c.source_filename,
                "chunk_index": c.chunk_index,
                "relevance_score": c.relevance_score,
                "excerpt": c.excerpt,
            }
            for c in answer_obj.citations
        ],
        "model_used": usage_dict.get("routed_model", ""),
        "synthesis_usage": [usage_dict],
    }





def should_continue(state: AgentState) -> str:
    """Route to tools if the agent just requested one, else to synthesize."""
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return "synthesize"


def should_verify(state: AgentState) -> str:
    """Route to verify only if enabled for this query and not disabled deployment wide."""
    if not state.get("enable_verifier", True):
        return "end"
    if not FEATURES.get("verifier_enabled", True):
        return "end"
    return "verify"


def verify_router(state: AgentState) -> str:
    """After verification: retry (back through agent_node) if something was
    flagged as unsupported and retries remain; otherwise end."""
    if not state.get("verified", True):
        last_msg = state["messages"][-1]
        if isinstance(last_msg, HumanMessage) and str(last_msg.content).startswith("[Verifier feedback]"):
            return "retry"
    return "end"


def build_agent_graph(adapters: Adapters):
    tools = [make_retrieve_tool(adapters), make_list_namespaces_tool(adapters)]
    reasoning_model = adapters.chat.chat_model(max_tokens=AGENT_MAX_TOKENS).bind_tools(tools)
    verifier_model = adapters.chat.chat_model(max_tokens=VERIFIER_MAX_TOKENS)
    cost_of = adapters.chat.cost

    async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]]
        ctx = gateway_from_config(config)
        if ctx is not None and ctx.halted:
            # A denial already ended this run: no more model calls, go straight to synthesis.
            return {"messages": [AIMessage(content="")], "reasoning_usage": []}
        question = next((str(m.content) for m in state["messages"] if isinstance(m, HumanMessage)), "")
        if not await _model_allowed(config, question, _estimate_tokens(messages, AGENT_MAX_TOKENS)):
            return {"messages": [AIMessage(content="")], "reasoning_usage": []}
        response = None
        for attempt in range(3):
            try:
                response = await reasoning_model.ainvoke(messages)
                break
            except Exception as e:
                if "rate_limit" in str(e).lower() and attempt < 2:
                    import asyncio
                    logger.warning("[agent] reasoning_model rate limited, waiting 35s (attempt %d)...", attempt + 1)
                    await asyncio.sleep(35)
                else:
                    raise
        if response is None:  # unreachable: the loop either breaks with a response or raises
            raise RuntimeError("Reasoning model returned no response")
        return {
            "messages": [response],
            "reasoning_usage": [_extract_llm_usage(response, cost_of)],
        }

    async def verify_node_inner(state: AgentState, config: RunnableConfig) -> dict:
        chunks = _extract_chunks(state["messages"])
        excerpts = "\n\n".join(
            f"[{c.get('document_id')}] {c.get('content', '')[:500]}" for c in chunks
        )
        ctx = gateway_from_config(config)
        if ctx is not None and ctx.halted:
            # A denial already ended this run: do not spend another model call verifying a partial answer.
            return {"verification_notes": f"Verification skipped: the run was cut short by policy ({ctx.halted}).",
                    "verifier_usage": []}
        draft = str(state.get("final_answer", ""))
        if not await _model_allowed(config, draft, estimate_tokens(draft + excerpts, VERIFIER_MAX_TOKENS)):
            return {"verification_notes": "Verification skipped: the model call is not permitted within your limits.",
                    "verifier_usage": []}
        response = await verifier_model.ainvoke([
            SystemMessage(content=VERIFIER_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Draft answer:\n{state['final_answer']}\n\nSource chunks:\n{excerpts}"
            ),
        ])

        try:
            parsed = json.loads(str(response.content))
            supported = bool(parsed.get("supported", True))
            notes = parsed.get("notes", "")
        except (json.JSONDecodeError, TypeError):
            supported = True
            notes = "Verifier response was not valid JSON; treated as supported."

        update = {
            "verified": supported,
            "verification_notes": notes,
            "verifier_usage": [_extract_llm_usage(response, cost_of)],
        }

        retries_left = state.get("verify_retries_left", 0)
        if not supported and retries_left > 0:
            update["verify_retries_left"] = retries_left - 1
            update["messages"] = [HumanMessage(
                content=f"[Verifier feedback] {notes} Please retrieve additional context to address this."
            )]

        return update

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("synthesize", make_synthesize_node(adapters))
    graph.add_node("verify", verify_node_inner)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "synthesize": "synthesize"})
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("synthesize", should_verify, {"verify": "verify", "end": END})
    graph.add_conditional_edges("verify", verify_router, {"retry": "agent", "end": END})

    return graph.compile()

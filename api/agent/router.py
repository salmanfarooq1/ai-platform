import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field

from api.agent.models import AGENT_MAX_TOKENS
from api.agent.runner import AGENT_RUN_KIND, AgentRunOutput
from api.auth import require_kb, require_scope
from api.dependencies import adapters_of
from api.gateway_deps import entry_action, gateway_context
from config import LLM_CONFIG, MODEL_PRICING
from core.identity.models import Principal, Scope
from gateway import Action, ActionKind, EnforcementContext, require
from gateway.estimate import estimate_tokens
from ports import RunSpec, RunState

logger = logging.getLogger("api.agent")
router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    question: str = Field(description="The compliance question to research")
    namespace: str = Field(default="default", description="Document scope hint for the agent")
    max_iterations: int = Field(default=6, ge=1, le=10, description="Max retrieve_chunks calls before forcing synthesis")
    enable_verifier: bool = Field(default=True, description="Whether to verify the drafted answer against retrieved chunks before returning it")
    max_verify_retries: int = Field(default=1, ge=0, le=3, description="How many times verification can send the query back for more retrieval")


class AgentCitation(BaseModel):
    """Mirrors schemas.py Citation exactly."""
    document_id: str
    source_filename: str
    chunk_index: int
    relevance_score: float
    excerpt: str


class AgentResponse(BaseModel):
    question: str
    answer: str
    confidence: float = 0.0
    citations: list[AgentCitation] = []
    model_used: str = ""
    verified: bool | None = None  # None means the verifier did not run for this query
    verification_notes: str = ""
    reasoning_steps: list[str]
    tool_calls_made: int
    total_time_seconds: float
    total_cost_usd: float = 0.0
    flagged: bool = False  # True when a gateway denial cut the run short: the answer is partial
    flag_reason: str | None = None


def _combine_usage(result: dict) -> dict:
    """Sum every reasoning role and verifier role LLM call usage with
    synthesize_node own cost, so FinOps sees an agent query full cost,
    not just its final step."""
    all_calls = (
        result.get("reasoning_usage", [])
        + result.get("verifier_usage", [])
        + result.get("synthesis_usage", [])
    )

    prompt_tokens = sum(u.get("prompt_tokens", 0) for u in all_calls)
    completion_tokens = sum(u.get("completion_tokens", 0) for u in all_calls)

    model = result.get("model_used", "")
    llm_cost = 0.0
    if model and not model.startswith("ollama/"):
        rates = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
        llm_cost = (prompt_tokens / 1_000_000) * rates["input"] + (completion_tokens / 1_000_000) * rates["output"]

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_cost": llm_cost,
        "routing_decision": "agent",
        "routed_model": result.get("model_used", ""),
        "model": result.get("model_used", ""),
    }


@router.post("/query", response_model=AgentResponse)
async def agent_query(
    request: Request,
    response: Response,
    payload: AgentRequest,
    principal: Principal = Depends(require_scope(Scope.AGENT)),
    ctx: EnforcementContext = Depends(gateway_context),
) -> AgentResponse:
    start = time.perf_counter()
    adapters = adapters_of(request)
    # The run's id is fixed before the first check, so every decision this request causes carries it.
    execution_id = uuid4()
    ctx.execution_id = execution_id
    # The gateway decides first: scope, input guardrails, rate limit and daily token budget.
    await require(ctx, entry_action(request.url.path, ActionKind.AGENT_RUN, input_text=payload.question))
    await require_kb(adapters.knowledge, principal, payload.namespace)
    # The model must be allowed before the run starts (each LLM call inside the run is checked again).
    await require(ctx, Action(
        ActionKind.MODEL_INVOKE, LLM_CONFIG["model"], estimated_tokens=estimate_tokens(payload.question, AGENT_MAX_TOKENS),
        input_text=payload.question,
    ))

    # The run goes through the AgentRuntime port (ADR-0009). The graph was compiled once at startup (main.py).
    handle = await adapters.runtime.start(RunSpec(
        kind=AGENT_RUN_KIND, input=payload.model_dump(), tenant_id=principal.tenant_id, context=ctx,
        execution_id=execution_id,
    ))
    try:
        outcome = await adapters.runtime.wait(handle.run_id)
    finally:
        # Also on a client disconnect (the handler is cancelled): cleanup stops a run that is still going.
        await adapters.runtime.cleanup(handle.run_id)

    if outcome.status.state is not RunState.SUCCEEDED:
        logger.error("[agent] run %s ended %s: %s", handle.run_id, outcome.status.state.value, outcome.status.error)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {outcome.status.error}")
    output: AgentRunOutput = outcome.output
    if output.result is None:
        return AgentResponse(
            question=payload.question,
            answer=(
                "I was not able to reach a confident answer within the allotted "
                "reasoning steps. Try a narrower question or a higher max_iterations."
            ),
            confidence=0.0,
            reasoning_steps=["Reached max_iterations without producing a final answer."],
            tool_calls_made=0,
            total_time_seconds=round(time.perf_counter() - start, 3),
        )
    result = output.result

    reasoning_steps = []
    tool_call_count = 0
    for msg in result["messages"]:
        if getattr(msg, "tool_calls", None):
            tool_call_count += len(msg.tool_calls)
            for tc in msg.tool_calls:
                reasoning_steps.append(f"Called tool: {tc['name']}({tc['args']})")
        elif isinstance(msg, ToolMessage):
            content = msg.content or ""
            suffix = "..." if len(content) > 200 else ""
            reasoning_steps.append(f"Tool result: {content[:200]}{suffix}")

    usage_dict = _combine_usage(result)
    usage_dict["namespace"] = payload.namespace
    request.state.usage = usage_dict
    response.headers["X-Cost-USD"] = f"{usage_dict['total_cost']:.6f}"

    flag_reason = None
    if ctx.denials:
        flag_reason = f"Run cut short by policy (reason: {ctx.denials[0].reason}). The answer is partial."

    return AgentResponse(
        question=payload.question,
        flagged=bool(ctx.denials),
        flag_reason=flag_reason,
        answer=result.get("final_answer", "No answer generated"),
        confidence=result.get("confidence", 0.0),
        citations=[AgentCitation(**c) for c in result.get("citations", [])],
        model_used=result.get("model_used", ""),
        verified=result.get("verified"),
        verification_notes=result.get("verification_notes", ""),
        reasoning_steps=reasoning_steps,
        tool_calls_made=tool_call_count,
        total_time_seconds=round(time.perf_counter() - start, 3),
        total_cost_usd=usage_dict["total_cost"],
    )

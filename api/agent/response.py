"""The result of one agent run, built from the graph's final state (moved here from the route in Sprint 007).

A worker builds it where the run happened, so the answer is stored with the job and a request that stopped
waiting can still read it. The route builds it itself only when the runtime hands back the raw output (the
in-process runtime). `usage` carries what FinOps needs: tokens, model and cost.
"""
import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import ToolMessage

from api.agent.runner import AgentRunOutput
from api.agent.schemas import AgentCitation, AgentResponse
from api.services.usage import record_usage as log_usage
from config import MODEL_PRICING
from core.database.tenant import DbPool, tenant_connection
from gateway import EnforcementContext, GatewayRuntime
from gateway.limits import record_usage as book_tokens

logger = logging.getLogger("api.agent.response")

NOT_CONFIDENT = (
    "I was not able to reach a confident answer within the allotted "
    "reasoning steps. Try a narrower question or a higher max_iterations."
)


def combine_usage(result: dict) -> dict:
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


def build_agent_result(
    output: AgentRunOutput, question: str, namespace: str, ctx: EnforcementContext | None, elapsed_seconds: float,
) -> dict[str, Any]:
    """`{"response": AgentResponse as a dict, "usage": usage dict or None}`. Pure: nothing is booked here."""
    if output.result is None:
        response = AgentResponse(
            question=question, answer=NOT_CONFIDENT, confidence=0.0,
            reasoning_steps=["Reached max_iterations without producing a final answer."],
            tool_calls_made=0, total_time_seconds=round(elapsed_seconds, 3),
        )
        return {"response": response.model_dump(mode="json"), "usage": None}
    result = output.result

    reasoning_steps: list[str] = []
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

    usage = combine_usage(result)
    usage["namespace"] = namespace

    denials = ctx.denials if ctx is not None else []
    flag_reason = None
    if denials:
        flag_reason = f"Run cut short by policy (reason: {denials[0].reason}). The answer is partial."

    response = AgentResponse(
        question=question,
        flagged=bool(denials),
        flag_reason=flag_reason,
        answer=result.get("final_answer", "No answer generated"),
        confidence=result.get("confidence", 0.0),
        citations=[AgentCitation(**c) for c in result.get("citations", [])],
        model_used=result.get("model_used", ""),
        verified=result.get("verified"),
        verification_notes=result.get("verification_notes", ""),
        reasoning_steps=reasoning_steps,
        tool_calls_made=tool_call_count,
        total_time_seconds=round(elapsed_seconds, 3),
        total_cost_usd=usage["total_cost"],
    )
    return {"response": response.model_dump(mode="json"), "usage": usage}


async def _first_booking(pool: DbPool, tenant_id: UUID, execution_id: UUID) -> bool:
    """Record the booking of this run in `processed_events`; False if it was recorded before. Fails open to a
    booking (a lost row of usage is worse than a rare repeat), and logs."""
    try:
        async with tenant_connection(pool, tenant_id) as conn:
            return bool(await conn.fetchval(
                "INSERT INTO processed_events (tenant_id, consumer, event_id) VALUES ($1, 'agent-usage', $2) "
                "ON CONFLICT DO NOTHING RETURNING 1", tenant_id, str(execution_id),
            ))
    except Exception:
        logger.warning("usage booking marker not written: execution_id=%s", execution_id, exc_info=True)
        return True


async def book_agent_usage(
    pool: DbPool, runtime: GatewayRuntime, tenant_id: UUID, request_id: str, usage: dict[str, Any],
    execution_id: UUID | None = None,
) -> dict[str, str]:
    """Book the run's tokens against the tenant's day and write its `usage_log` row, at most once per
    `execution_id` (a run that a second worker re-claimed after a crash does not book again; the first claim wins).
    Best effort, as the middleware always was: the work is done. Returns the budget headers (maybe empty)."""
    if execution_id is not None and not await _first_booking(pool, tenant_id, execution_id):
        return {}
    total = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    headers: dict[str, str] = {}
    try:
        if total > 0:
            headers = await book_tokens(runtime, tenant_id, total)
        await log_usage(
            pool=pool, tenant_id=tenant_id, request_id=request_id, endpoint="/v1/agent/query",
            namespace=usage.get("namespace", "global"), model=usage.get("model", "unknown"),
            prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
            cost_usd=usage.get("total_cost", 0.0), routing_decision=usage.get("routing_decision", ""),
        )
    except Exception:
        logger.warning("agent usage not booked: request_id=%s", request_id, exc_info=True)
    return headers

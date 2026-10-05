"""The runner the in-process `AgentRuntime` executes for `/v1/agent/query`: it wraps the compiled LangGraph agent.

The runtime (ADR-0009) owns the lifecycle (start, status, stop, cleanup). This module only does the work of
one run. The enforcement context reaches the graph nodes and tools through `configurable`, never through
model-controlled arguments, and carries the run's `execution_id` so every decision the run causes records it.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

from gateway import EnforcementContext
from ports import RunSpec

logger = logging.getLogger("api.agent.runner")

AGENT_RUN_KIND = "agent.query"


@dataclass(frozen=True)
class AgentRunOutput:
    """`result` is the graph's final state; None when the run hit the recursion limit before converging."""

    result: dict[str, Any] | None
    recursion_limit: int | None = None


def recursion_limit_for(max_iterations: int, max_verify_retries: int) -> int:
    # Generous upper bound, not a tight derivation.
    base_round = max_iterations * 2 + 2
    return base_round * (1 + max_verify_retries) + max_verify_retries + 5


def make_agent_runner(get_graph: Callable[[], Any]):
    """A `Runner` for `RunSpec(kind="agent.query")`. `get_graph` returns the graph compiled at startup."""

    async def run(spec: RunSpec) -> AgentRunOutput:
        ctx = spec.context
        if not isinstance(ctx, EnforcementContext):
            raise TypeError("an agent run needs an EnforcementContext")
        ctx.execution_id = spec.execution_id
        payload = spec.input
        limit = recursion_limit_for(payload["max_iterations"], payload["max_verify_retries"])
        try:
            result = await get_graph().ainvoke(
                {
                    "messages": [HumanMessage(content=payload["question"])],
                    # Both reducer typed lists MUST be initialized here.
                    # Omitting them raises InvalidUpdateError the first time
                    # agent_node tries to append.
                    "reasoning_usage": [],
                    "verifier_usage": [],
                    "synthesis_usage": [],
                    "enable_verifier": payload["enable_verifier"],
                    "verify_retries_left": payload["max_verify_retries"],
                },
                config={"recursion_limit": limit, "configurable": {"gateway": ctx}},
            )
        except GraphRecursionError:
            logger.warning(  # never the question text: logs must not hold input text
                "[agent] hit recursion_limit=%d before converging, execution_id=%s", limit, spec.execution_id,
            )
            return AgentRunOutput(result=None, recursion_limit=limit)
        return AgentRunOutput(result=result)

    return run

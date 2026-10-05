"""The routes a sandboxed agent calls (Sprint 009, ADR-0009).

They accept a run token only, and only for their own run: `/v1/sandbox/runs/{execution_id}/...`. The auth middleware
rejects the token on any other route and for any other run. The boundary comes from the token (fixed when the run
was accepted), the tenant and principal from the token's row, and every call goes through `enforce()` and writes a
decision row with the run's `execution_id`. The sandbox has no model key and no database: these two routes are its
whole reach.
"""
import json
import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from api.agent.models import AGENT_MAX_TOKENS
from api.agent.response import book_agent_usage
from api.agent.tools import make_list_namespaces_tool, make_retrieve_tool
from api.dependencies import adapters_of
from api.observability import current_request_id, current_trace_id
from config import LLM_CONFIG
from core.identity.run_tokens import RunGrant
from gateway import Action, ActionKind, EnforcementContext, GatewayDenied, GatewayRuntime, require
from gateway.context import run_context
from gateway.estimate import estimate_tokens

logger = logging.getLogger("api.sandbox")
router = APIRouter(prefix="/sandbox", tags=["sandbox"])

MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 20_000


class ToolCall(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict, description="The arguments of the tool call. The policy may check them against a schema.")


class ToolResult(BaseModel):
    result: Any = Field(description="What the tool returned (JSON text for the retrieval tool)")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)


class ModelCall(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    max_tokens: int = Field(default=1024, ge=1, le=AGENT_MAX_TOKENS)


class ModelUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_cost: float


class ModelResult(BaseModel):
    text: str
    model: str
    usage: ModelUsage


# A fault is not a policy decision: the standard 503, as on every other route (Sprint 009 QA M1).
_FAULTS = ("decision_unrecorded", "internal_error")


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail={"error": "service_unavailable", "reason": "A required service is unavailable. Try again shortly."})


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "forbidden", "reason": "A run token is needed for this route"})


async def run_grant(request: Request, execution_id: UUID) -> RunGrant:
    """The run token's grant, for this run only. Anything else is a 403 (the middleware has already refused other paths)."""
    grant = getattr(request.state, "run_grant", None)
    if not isinstance(grant, RunGrant) or grant.execution_id != execution_id:
        raise _forbidden()
    return grant


async def run_ctx(request: Request, grant: RunGrant = Depends(run_grant)) -> EnforcementContext:
    runtime: GatewayRuntime = request.app.state.gateway_runtime
    request_id = str(getattr(request.state, "request_id", None) or current_request_id())
    trace_id = str(getattr(request.state, "trace_id", None) or current_trace_id())
    return await run_context(runtime, grant.principal, grant.boundary, grant.execution_id, request_id, trace_id)


@router.post("/runs/{execution_id}/tools/{name}", response_model=ToolResult)
async def call_tool(
    request: Request, execution_id: UUID, name: str, body: ToolCall, ctx: EnforcementContext = Depends(run_ctx),
) -> ToolResult:
    """One tool call by a sandboxed agent. The gateway checks the tool, its arguments and the data it reads."""
    adapters = adapters_of(request)
    tools = {"retrieve_chunks": make_retrieve_tool(adapters), "list_namespaces": make_list_namespaces_tool(adapters)}
    tool = tools.get(name)
    if tool is None:
        raise HTTPException(status_code=404, detail={"error": "unknown_tool", "reason": "No such tool"})
    try:
        raw = await tool.ainvoke(body.arguments, config={"configurable": {"gateway": ctx}})
    except ValidationError:  # arguments the tool cannot take (wrong type, unknown name)
        raise HTTPException(status_code=422, detail="The tool arguments are not valid") from None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and "error" in parsed:
        code = str(parsed["error"])
        reason = str(parsed.get("reason", code))
        if code == "policy_denied" and reason in _FAULTS:
            raise _unavailable()
        if code == "policy_denied":
            raise HTTPException(status_code=403, detail={"error": "policy_denied", "reason": f"Denied by policy (reason: {reason})"})
        if code == "kb_not_found":
            raise HTTPException(status_code=404, detail={"error": "kb_not_found", "reason": reason})
        logger.error("sandbox tool %s failed: execution_id=%s", name, execution_id)
        raise HTTPException(status_code=500, detail={"error": "tool_failed", "reason": "The tool failed"})
    return ToolResult(result=raw)


@router.post("/runs/{execution_id}/model", response_model=ModelResult)
async def call_model(
    request: Request, execution_id: UUID, body: ModelCall, ctx: EnforcementContext = Depends(run_ctx),
) -> ModelResult:
    """One model call by a sandboxed agent. The gateway checks the model and the token cap, the platform makes the call
    (the sandbox has no provider key) and books the usage against the tenant."""
    adapters = adapters_of(request)
    text = "\n".join(m.content for m in body.messages)
    model = LLM_CONFIG["model"]
    try:
        await require(ctx, Action(
            ActionKind.MODEL_INVOKE, model, estimated_tokens=estimate_tokens(text, body.max_tokens), input_text=text,
        ))
    except GatewayDenied as exc:
        if exc.decision.reason in _FAULTS:
            raise _unavailable() from None
        raise
    try:
        completion = await adapters.llm.complete([m.model_dump() for m in body.messages], model=model, max_tokens=body.max_tokens)
    except Exception:
        logger.error("sandbox model call failed: execution_id=%s", execution_id, exc_info=True)
        raise HTTPException(status_code=502, detail={"error": "model_failed", "reason": "The model call failed"}) from None
    usage = {
        "prompt_tokens": completion.tokens_in, "completion_tokens": completion.tokens_out, "total_cost": completion.cost_usd,
        "model": completion.model, "routing_decision": "agent", "namespace": "sandbox",
    }
    principal = ctx.principal
    assert principal is not None
    await book_agent_usage(request.app.state.db_pool, request.app.state.gateway_runtime, principal.tenant_id, ctx.request_id, usage)
    return ModelResult(
        text=completion.text, model=completion.model,
        usage=ModelUsage(prompt_tokens=completion.tokens_in, completion_tokens=completion.tokens_out, total_cost=completion.cost_usd),
    )

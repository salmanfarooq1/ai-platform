"""Run-token authorization shared by enabled and disabled sandbox routes.

This foundation module imports no agent, MCP or sandbox execution code.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from api.observability import current_request_id, current_trace_id
from core.identity.run_tokens import RunGrant
from gateway import EnforcementContext, GatewayRuntime
from gateway.context import run_context


async def run_grant(request: Request, execution_id: UUID) -> RunGrant:
    """A verified grant bound to this exact run; ordinary credentials do not suffice."""
    grant = getattr(request.state, "run_grant", None)
    if not isinstance(grant, RunGrant) or grant.execution_id != execution_id:
        raise HTTPException(status_code=403, detail={
            "error": "forbidden", "reason": "A run token is needed for this route",
        })
    return grant


async def run_ctx(request: Request, grant: RunGrant = Depends(run_grant)) -> EnforcementContext:
    runtime: GatewayRuntime = request.app.state.gateway_runtime
    request_id = str(getattr(request.state, "request_id", None) or current_request_id())
    trace_id = str(getattr(request.state, "trace_id", None) or current_trace_id())
    return await run_context(runtime, grant.principal, grant.boundary, grant.execution_id, request_id, trace_id,
                             required_module="agents")

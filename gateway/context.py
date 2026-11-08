"""Build the per-request enforcement context: load the tenant's active policy once, fix the boundary."""
import logging
from typing import Any
from uuid import UUID

from core.database.tenant import tenant_connection
from core.identity.models import Principal, parse_scopes
from gateway import policy as policy_module
from gateway.boundary import ExecutionBoundary, build_boundary, deny_all_boundary
from gateway.types import EnforcementContext, GatewayRuntime

logger = logging.getLogger("gateway.context")


async def build_context(
    runtime: GatewayRuntime,
    principal: Principal,
    request_id: str,
    trace_id: str,
    headers: dict[str, str] | None = None,
    required_module: str | None = None,
) -> EnforcementContext:
    """The boundary is fixed here for the whole request (a policy change mid-request does not apply).

    If the active policy cannot be read or parsed, the boundary denies everything (fail closed) and the
    error is logged.
    """
    try:
        doc, version = await policy_module.load_active_policy(runtime.pool, principal.tenant_id)
        boundary = build_boundary(principal, doc, version)
    except Exception:
        logger.error("active policy unavailable for tenant %s, denying all actions", principal.tenant_id, exc_info=True)
        boundary = deny_all_boundary(principal.tenant_id, "policy_unavailable")
    return EnforcementContext(
        principal=principal,
        request_id=request_id,
        trace_id=trace_id,
        boundary=boundary,
        runtime=runtime,
        headers=headers if headers is not None else {},
        required_module=required_module,
    )


def context_to_payload(ctx: EnforcementContext) -> dict[str, Any]:
    """The part of a request's context a worker needs to act for it: who, which request, and the fixed boundary.
    It is JSON, holds no secret and no input text, and is what a queued agent run carries (ADR-0009, ADR-0011)."""
    principal = ctx.principal
    return {
        "principal": None if principal is None else {
            "id": str(principal.id), "tenant_id": str(principal.tenant_id), "kind": principal.kind,
            "scopes": sorted(principal.scopes),
            "credential_id": str(principal.credential_id) if principal.credential_id else None,
        },
        "request_id": ctx.request_id,
        "trace_id": ctx.trace_id,
        "boundary": ctx.boundary.to_payload(),
        "execution_id": str(ctx.execution_id) if ctx.execution_id else None,
        "required_module": ctx.required_module,
    }


def context_from_payload(runtime: GatewayRuntime, body: dict[str, Any]) -> EnforcementContext:
    """Rebuild the context in a worker. The boundary is the one fixed when the request started (strict rule 3):
    a policy published since then does not widen or narrow a run that was already accepted."""
    raw = body["principal"]
    principal = None if raw is None else Principal(
        id=UUID(raw["id"]), tenant_id=UUID(raw["tenant_id"]), kind=raw["kind"], scopes=parse_scopes(raw["scopes"]),
        credential_id=UUID(raw["credential_id"]) if raw.get("credential_id") else None,
    )
    return EnforcementContext(
        principal=principal, request_id=body["request_id"], trace_id=body["trace_id"],
        boundary=ExecutionBoundary.from_payload(body["boundary"]), runtime=runtime,
        execution_id=UUID(body["execution_id"]) if body.get("execution_id") else None,
        required_module=body.get("required_module"),
    )


async def count_run_tool_calls(runtime: GatewayRuntime, tenant_id: UUID, execution_id: UUID) -> int:
    """Tool calls a run was allowed so far. Each call to the gateway is a new request, so the per-run limit
    (`max_tool_calls`) is counted from the decision rows of the run, not from memory."""
    async with tenant_connection(runtime.pool, tenant_id) as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM gateway_decisions WHERE execution_id = $1 AND action = 'tool.call' AND outcome = 'allow'",
            execution_id,
        )
    return int(count or 0)


async def run_context(
    runtime: GatewayRuntime, principal: Principal, boundary: dict[str, Any], execution_id: UUID,
    request_id: str, trace_id: str, required_module: str | None = "agents",
) -> EnforcementContext:
    """The context of one call a sandboxed agent makes. The boundary is the one the run was accepted with (it travelled
    in the run token), so a policy published since then does not change a run that is already going (strict rule 3)."""
    ctx = EnforcementContext(
        principal=principal, request_id=request_id, trace_id=trace_id,
        boundary=ExecutionBoundary.from_payload(boundary), runtime=runtime, execution_id=execution_id,
        required_module=required_module,
    )
    ctx.tool_calls = await count_run_tool_calls(runtime, principal.tenant_id, execution_id)
    return ctx

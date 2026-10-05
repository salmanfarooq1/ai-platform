"""Build the per-request enforcement context: load the tenant's active policy once, fix the boundary."""
import logging
from typing import Any
from uuid import UUID

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
    )


def context_to_payload(ctx: EnforcementContext) -> dict[str, Any]:
    """The part of a request's context a worker needs to act for it: who, which request, and the fixed boundary.
    It is JSON, holds no secret and no input text, and is what a queued agent run carries (ADR-0009, ADR-0011)."""
    principal = ctx.principal
    return {
        "principal": None if principal is None else {
            "id": str(principal.id), "tenant_id": str(principal.tenant_id), "kind": principal.kind,
            "scopes": sorted(principal.scopes),
        },
        "request_id": ctx.request_id,
        "trace_id": ctx.trace_id,
        "boundary": ctx.boundary.to_payload(),
        "execution_id": str(ctx.execution_id) if ctx.execution_id else None,
    }


def context_from_payload(runtime: GatewayRuntime, body: dict[str, Any]) -> EnforcementContext:
    """Rebuild the context in a worker. The boundary is the one fixed when the request started (strict rule 3):
    a policy published since then does not widen or narrow a run that was already accepted."""
    raw = body["principal"]
    principal = None if raw is None else Principal(
        id=UUID(raw["id"]), tenant_id=UUID(raw["tenant_id"]), kind=raw["kind"], scopes=parse_scopes(raw["scopes"]),
    )
    return EnforcementContext(
        principal=principal, request_id=body["request_id"], trace_id=body["trace_id"],
        boundary=ExecutionBoundary.from_payload(body["boundary"]), runtime=runtime,
        execution_id=UUID(body["execution_id"]) if body.get("execution_id") else None,
    )

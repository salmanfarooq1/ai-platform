"""Build the per-request enforcement context: load the tenant's active policy once, fix the boundary."""
import logging

from core.identity.models import Principal
from gateway import policy as policy_module
from gateway.boundary import build_boundary, deny_all_boundary
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

"""Startup check for the configured tenant deployment shape."""
from core.database.tenant import DbPool


async def assert_deploy_shape(pool: DbPool, deploy_shape: str) -> None:
    """Reject a single-tenant process pointed at a database with multiple tenants."""
    if deploy_shape not in {"single_tenant", "multi_tenant"}:
        raise ValueError("deploy shape must be single_tenant or multi_tenant")
    has_multiple = await pool.fetchval("SELECT deploy_shape_has_multiple_tenants()")
    if deploy_shape == "single_tenant" and has_multiple:
        raise RuntimeError("single_tenant deployment requires at most one tenant; set DEPLOY_SHAPE=multi_tenant")

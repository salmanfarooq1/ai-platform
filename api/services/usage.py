"""
Async usage log writer.

Provides a single function that the FinOps middleware calls to persist
one usage row per request. The write is fire-and-forget (errors are
logged, never raised) so a Postgres hiccup cannot crash or slow down
a user-facing response.
"""
import logging
from uuid import UUID

from asyncpg import Pool

from core.database.tenant import tenant_connection

logger = logging.getLogger("api.usage")


async def record_usage(
    pool: Pool,
    tenant_id: UUID,
    request_id: str,
    endpoint: str,
    namespace: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    routing_decision: str = "",
) -> None:
    """Insert one usage row. Errors are swallowed and logged."""
    try:
        async with tenant_connection(pool, tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO usage_log
                    (tenant_id, request_id, endpoint, namespace, model,
                     prompt_tokens, completion_tokens, cost_usd,
                     routing_decision)
                VALUES ($9, $1, $2, $3, $4, $5, $6, $7, $8)
                """,
                request_id,
                endpoint,
                namespace,
                model,
                prompt_tokens,
                completion_tokens,
                cost_usd,
                routing_decision,
                tenant_id,
            )
    except Exception as e:
        logger.warning("[usage] Failed to persist usage row: %s", e)

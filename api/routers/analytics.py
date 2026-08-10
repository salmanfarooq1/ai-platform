"""
api/routers/analytics.py

Cost and usage analytics derived from the usage_log table.
Powers the frontend Analytics dashboard.

All queries are read-only against usage_log, which is written by
FinOpsMiddleware after every /search and /agent/query response.
"""
from datetime import datetime, timedelta, timezone

from asyncpg import Pool
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool


@router.get("/summary")
async def analytics_summary(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to look back"),
    pool: Pool = Depends(get_db_pool),
):
    """Return cost and usage breakdown for the last N days.

    Breaks down total spend and request volume by day, endpoint,
    namespace, and model. Used to power the frontend Analytics page.
    All figures are derived from the usage_log table written by
    FinOpsMiddleware.

    Prerequisite: namespace is only accurate after the cache-hit namespace
    fix (bug 1.2) — rows written before that fix carry namespace='global'.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with pool.acquire() as conn:
        totals = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS total_tokens,
                COUNT(*) AS total_requests
            FROM usage_log
            WHERE created_at >= $1
            """,
            since,
        )
        by_day = await conn.fetch(
            """
            SELECT
                created_at::date AS date,
                SUM(cost_usd) AS cost_usd,
                SUM(prompt_tokens + completion_tokens) AS tokens,
                COUNT(*) AS requests
            FROM usage_log
            WHERE created_at >= $1
            GROUP BY 1
            ORDER BY 1
            """,
            since,
        )
        by_endpoint = await conn.fetch(
            """
            SELECT
                endpoint,
                SUM(cost_usd) AS cost_usd,
                COUNT(*) AS requests
            FROM usage_log
            WHERE created_at >= $1
            GROUP BY 1
            ORDER BY cost_usd DESC
            """,
            since,
        )
        by_namespace = await conn.fetch(
            """
            SELECT
                namespace,
                SUM(cost_usd) AS cost_usd,
                COUNT(*) AS requests
            FROM usage_log
            WHERE created_at >= $1
            GROUP BY 1
            ORDER BY cost_usd DESC
            """,
            since,
        )
        by_model = await conn.fetch(
            """
            SELECT
                model,
                SUM(cost_usd) AS cost_usd,
                COUNT(*) AS requests
            FROM usage_log
            WHERE created_at >= $1
            GROUP BY 1
            ORDER BY cost_usd DESC
            """,
            since,
        )

    total_requests = totals["total_requests"] or 0
    total_cost = float(totals["total_cost_usd"] or 0)
    total_tokens = int(totals["total_tokens"] or 0)

    return {
        "days": days,
        "total_cost_usd": total_cost,
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "avg_cost_per_request": (total_cost / total_requests) if total_requests else 0.0,
        "by_day": [
            {
                "date": str(r["date"]),
                "cost_usd": float(r["cost_usd"]),
                "tokens": int(r["tokens"]),
                "requests": r["requests"],
            }
            for r in by_day
        ],
        "by_endpoint": [
            {"endpoint": r["endpoint"], "cost_usd": float(r["cost_usd"]), "requests": r["requests"]}
            for r in by_endpoint
        ],
        "by_namespace": [
            {"namespace": r["namespace"], "cost_usd": float(r["cost_usd"]), "requests": r["requests"]}
            for r in by_namespace
        ],
        "by_model": [
            {"model": r["model"], "cost_usd": float(r["cost_usd"]), "requests": r["requests"]}
            for r in by_model
        ],
    }

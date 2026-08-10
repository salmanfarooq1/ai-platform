"""
api/routers/feedback.py

Per-answer thumbs up/down feedback collection and quality reporting.

POST /feedback   — store a rating tied to a specific request_id (X-Query-ID)
GET  /quality-report — aggregate thumbs up/down counts by endpoint

The request_id passed in POST /feedback must match the X-Query-ID header
returned by /search or /agent/query. This allows the quality report to be
joined with usage_log for deeper analysis if needed.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(tags=["feedback"])


async def get_db_pool(request: Request) -> Pool:
    return request.app.state.db_pool


class FeedbackRequest(BaseModel):
    request_id: str
    endpoint: str
    rating: Literal["up", "down"]
    comment: str | None = None


@router.post("/feedback", status_code=201)
async def submit_feedback(
    payload: FeedbackRequest,
    pool: Pool = Depends(get_db_pool),
):
    """Record a thumbs up or down rating for a specific response.

    request_id must be the X-Query-ID header value from the original
    /search or /agent/query response. This ties the feedback row back
    to the exact request in usage_log.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback (request_id, endpoint, rating, comment)
                VALUES ($1, $2, $3, $4)
                """,
                payload.request_id,
                payload.endpoint,
                payload.rating,
                payload.comment,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")

    return {"status": "recorded"}


@router.get("/quality-report")
async def quality_report(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    pool: Pool = Depends(get_db_pool),
):
    """Return thumbs up/down counts aggregated by endpoint.

    Use this to track answer quality trends over time. A rising
    thumbs-down rate indicates a retrieval or generation regression.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                endpoint,
                COUNT(*) FILTER (WHERE rating = 'up')   AS thumbs_up,
                COUNT(*) FILTER (WHERE rating = 'down') AS thumbs_down,
                COUNT(*) AS total
            FROM feedback
            WHERE created_at >= $1
            GROUP BY endpoint
            ORDER BY total DESC
            """,
            since,
        )

    return {
        "days": days,
        "by_endpoint": [
            {
                "endpoint": r["endpoint"],
                "thumbs_up": r["thumbs_up"],
                "thumbs_down": r["thumbs_down"],
                "total": r["total"],
                "approval_rate": (
                    round(r["thumbs_up"] / r["total"], 3) if r["total"] else None
                ),
            }
            for r in rows
        ],
    }

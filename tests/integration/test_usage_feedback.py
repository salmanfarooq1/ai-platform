"""usage_log and feedback writes against real Postgres."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from api.routers.feedback import FeedbackRequest, quality_report, submit_feedback
from api.services.usage import record_usage
from tests.db_fixtures import principal_of


async def test_record_usage_writes_a_row_with_exact_values(db_pool, owner_pool, tenant_a):
    await record_usage(
        pool=db_pool, tenant_id=UUID(tenant_a.id), request_id="req-1", endpoint="/v1/search", namespace="legal",
        model="azure/gpt-4o", prompt_tokens=120, completion_tokens=30,
        cost_usd=0.0006, routing_decision="single",
    )

    row = await owner_pool.fetchrow("SELECT * FROM usage_log")
    assert row["tenant_id"] == UUID(tenant_a.id)
    assert row["request_id"] == "req-1"
    assert row["endpoint"] == "/v1/search"
    assert row["namespace"] == "legal"
    assert row["model"] == "azure/gpt-4o"
    assert (row["prompt_tokens"], row["completion_tokens"]) == (120, 30)
    assert row["cost_usd"] == Decimal("0.00060000")
    assert row["routing_decision"] == "single"
    assert row["created_at"] is not None


async def test_record_usage_swallows_database_errors(db_pool, owner_pool, tenant_a):
    # model is VARCHAR(200): an oversize value makes Postgres reject the insert.
    await record_usage(
        pool=db_pool, tenant_id=UUID(tenant_a.id), request_id="req-2", endpoint="/v1/search", namespace="legal",
        model="m" * 500, prompt_tokens=1, completion_tokens=1, cost_usd=0.0,
    )
    assert await owner_pool.fetchval("SELECT count(*) FROM usage_log") == 0


_REQUEST = SimpleNamespace(url=SimpleNamespace(path="/v1/feedback"))  # the routes only read the path


async def _ctx(pool, principal):
    from gateway import build_context
    from tests.gateway_helpers import make_runtime

    return await build_context(make_runtime(pool=pool), principal, "req-test", "t" * 32)


async def test_feedback_is_stored_and_reported(db_pool, owner_pool, tenant_a):
    principal = principal_of(tenant_a)
    ctx = await _ctx(owner_pool, principal)
    for rating in ("up", "up", "down"):
        result = await submit_feedback(
            FeedbackRequest(request_id="req-9", endpoint="/v1/search", rating=rating, comment="c"), request=_REQUEST,
            pool=db_pool, principal=principal, ctx=ctx,
        )
        assert result == {"status": "recorded"}

    rows = await owner_pool.fetch("SELECT request_id, endpoint, rating, comment FROM feedback ORDER BY id")
    assert [r["rating"] for r in rows] == ["up", "up", "down"]
    assert {(r["request_id"], r["endpoint"], r["comment"]) for r in rows} == {("req-9", "/v1/search", "c")}

    report = await quality_report(request=_REQUEST, days=7, pool=db_pool, principal=principal, ctx=ctx)
    assert report == {
        "days": 7,
        "by_endpoint": [
            {"endpoint": "/v1/search", "thumbs_up": 2, "thumbs_down": 1, "total": 3, "approval_rate": 0.667},
        ],
    }


async def test_feedback_check_constraint_rejects_bad_rating(owner_pool, tenant_a):
    with pytest.raises(Exception, match="feedback_rating_check"):
        await owner_pool.execute(
            "INSERT INTO feedback (tenant_id, request_id, endpoint, rating) VALUES ($1, 'r', '/v1/search', 'maybe')",
            UUID(tenant_a.id),
        )


async def test_submit_feedback_maps_database_failure_to_500(db_pool, owner_pool, tenant_a):
    principal = principal_of(tenant_a)
    ctx = await _ctx(owner_pool, principal)  # the decision record uses a healthy pool; the feedback pool is closed
    await db_pool.close()
    with pytest.raises(HTTPException) as exc:
        await submit_feedback(FeedbackRequest(request_id="r", endpoint="/v1/search", rating="up"), request=_REQUEST,
                              pool=db_pool, principal=principal, ctx=ctx)
    assert exc.value.status_code == 500

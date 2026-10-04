"""Tests for usage persistence service."""
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_record_usage_swallows_db_errors():
    """A Postgres failure must not propagate — it is fire-and-forget."""
    from api.services.usage import record_usage

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
    mock_conn.transaction = MagicMock(return_value=_async_cm(None))
    mock_pool.acquire = MagicMock(return_value=_async_cm(mock_conn))

    await record_usage(
        pool=mock_pool,
        tenant_id=UUID("00000000-0000-0000-0000-0000000000aa"),
        request_id="test-123",
        endpoint="/search",
        namespace="legal",
        model="groq/meta-llama/llama-4-scout-17b-16e-instruct",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.00003,
    )

    mock_conn.execute.assert_awaited_once()  # the failure came from the database call, and was swallowed


class _async_cm:
    """Minimal async context manager wrapper for mock connections."""
    def __init__(self, obj):
        self._obj = obj
    async def __aenter__(self):
        return self._obj
    async def __aexit__(self, *args):
        pass

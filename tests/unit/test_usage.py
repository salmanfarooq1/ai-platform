"""Tests for usage persistence service."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_record_usage_swallows_db_errors():
    """A Postgres failure must not propagate — it is fire-and-forget."""
    from api.services.usage import record_usage

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
    mock_pool.acquire = MagicMock(return_value=_async_cm(mock_conn))

    await record_usage(
        pool=mock_pool,
        request_id="test-123",
        endpoint="/search",
        namespace="legal",
        model="groq/meta-llama/llama-4-scout-17b-16e-instruct",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.00003,
    )


class _async_cm:
    """Minimal async context manager wrapper for mock connections."""
    def __init__(self, obj):
        self._obj = obj
    async def __aenter__(self):
        return self._obj
    async def __aexit__(self, *args):
        pass

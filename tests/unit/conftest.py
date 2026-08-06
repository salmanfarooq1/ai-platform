"""
tests/unit/conftest.py

Fixtures shared across unit tests only.
"""
import pytest


@pytest.fixture
def make_doc():
    """Factory fixture for creating minimal retriever document dicts.

    Usage: doc = make_doc(1, score_field="bm25_score", score=5.0)
    """
    def _make(id: int, content: str = "test", score_field: str = "bm25_score", score: float = 1.0) -> dict:
        return {
            "id": id,
            "document_id": f"doc_{id}",
            "content": content,
            "metadata": {},
            "source_filename": "test.md",
            score_field: score,
        }
    return _make


class AsyncContextManager:
    """Reusable async context manager mock for DB connections."""
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def mock_db_pool():
    """Create a mock asyncpg Pool with a working acquire() context manager.

    Usage:
        def test_something(mock_db_pool):
            pool, conn = mock_db_pool
            conn.fetch.return_value = [...]
    """
    from unittest.mock import AsyncMock, MagicMock
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncContextManager(conn))
    return pool, conn

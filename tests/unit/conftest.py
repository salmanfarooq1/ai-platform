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
    # tenant_connection opens a transaction on the connection.
    conn.transaction = MagicMock(return_value=AsyncContextManager(None))
    pool.acquire = MagicMock(return_value=AsyncContextManager(conn))
    return pool, conn


class GatewayIO:
    """What the gateway would read from and write to Postgres, held in memory for unit tests.

    `policy` is what `load_active_policy` returns (None means the platform default). `decisions` collects
    every decision record as (action kind, resource, outcome, stage, reason).
    """

    def __init__(self):
        self.policy = (None, None)
        self.decisions: list[tuple[str, str | None, str, str, str]] = []

    @property
    def reasons(self) -> list[str]:
        return [d[4] for d in self.decisions]


@pytest.fixture(autouse=True)
def gateway_io(monkeypatch):
    """Unit tests never reach Postgres: the policy loader and the decision writer are replaced."""
    import evidence.record
    import gateway.policy

    io = GatewayIO()

    async def load_active_policy(pool, tenant_id):
        return io.policy

    async def write_decision(pool, entry, events=None):
        io.decisions.append((entry.action, entry.resource, entry.outcome, entry.stage, entry.reason))

    monkeypatch.setattr(gateway.policy, "load_active_policy", load_active_policy)
    monkeypatch.setattr(evidence.record, "write_decision", write_decision)
    return io

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

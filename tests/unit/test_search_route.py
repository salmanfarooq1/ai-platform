"""Tests for /search route request schema validation."""
import pytest

from api.models.schemas import SearchRequest


def test_search_request_defaults():
    """SearchRequest should have sensible defaults."""
    req = SearchRequest(query="What is GDPR?")
    assert req.namespace == "default"
    assert req.query == "What is GDPR?"
    assert req.top_k == 5
    assert req.retrieval_mode == "hybrid"
    assert req.rerank is True


def test_search_request_accepts_custom_namespace():
    """Namespace override should work."""
    req = SearchRequest(query="test", namespace="legal")
    assert req.namespace == "legal"


def test_search_request_clamps_top_k():
    """top_k has ge=1, le=50 constraints from the Field validator."""
    with pytest.raises(Exception):
        SearchRequest(query="test", top_k=0)
    with pytest.raises(Exception):
        SearchRequest(query="test", top_k=100)


def test_search_request_validates_retrieval_mode():
    """retrieval_mode must match the regex pattern."""
    with pytest.raises(Exception):
        SearchRequest(query="test", retrieval_mode="invalid")

    # Valid modes should work
    for mode in ("vector_only", "bm25_only", "hybrid"):
        req = SearchRequest(query="test", retrieval_mode=mode)
        assert req.retrieval_mode == mode

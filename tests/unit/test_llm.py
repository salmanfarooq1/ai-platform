"""
tests/unit/test_llm.py

Tests for the query complexity classifier (pure function, no LLM call needed).
"""
import pytest
from api.services.llm import classify_query_complexity


@pytest.mark.parametrize("query", [
    "What is GDPR?",
    "What is CCPA?",
    "What is KYC?",
])
def test_simple_what_is_queries(query):
    """'What is X?' queries should be classified as simple."""
    assert classify_query_complexity(query) == "simple"


@pytest.mark.parametrize("query", [
    "Compare GDPR and CCPA fine structures",
    "Contrast Article 5 and Article 6 of GDPR",
    "Explain the implications of data minimization",
    "How does the HNSW algorithm work?"
])
def test_complex_comparison_queries(query):
    """Queries with comparison/reasoning keywords should be classified as complex."""
    assert classify_query_complexity(query) == "complex"


def test_complex_default_for_ambiguous():
    """Ambiguous queries should default to complex (safer to over-provision)."""
    assert classify_query_complexity("tell me about article 5") == "complex"


def test_empty_query_does_not_crash():
    """An empty string is a valid (if useless) input and must not raise."""
    result = classify_query_complexity("")
    assert result in ("simple", "complex")

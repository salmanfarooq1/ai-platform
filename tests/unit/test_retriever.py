"""
tests/unit/test_retriever.py

Tests for the retriever's pure functions (no database needed).
"""
import pytest
from api.services.retriever import rrf_merge


def test_rrf_empty_inputs():
    """RRF merge with no results from either source returns an empty list."""
    assert rrf_merge([], [], k=60, top_k=5) == []


def test_rrf_single_bm25_result(make_doc):
    """A single BM25 result passes through with the correct RRF score."""
    doc = make_doc(1, score_field="bm25_score", score=5.0)
    result = rrf_merge([doc], [], k=60, top_k=5)
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert abs(result[0]["rrf_score"] - 1.0 / 61) < 1e-6


def test_rrf_single_vector_result(make_doc):
    """A vector-only result should be scored identically to a BM25-only one at the same rank."""
    doc = make_doc(1, score_field="vector_score", score=0.9)
    result = rrf_merge([], [doc], k=60, top_k=5)
    assert len(result) == 1
    assert abs(result[0]["rrf_score"] - 1.0 / 61) < 1e-6


def test_rrf_duplicate_combined_score(make_doc):
    """Same chunk appearing in both lists gets a combined RRF score."""
    doc = make_doc(1)
    result = rrf_merge([doc], [doc], k=60, top_k=5)
    assert len(result) == 1
    expected = 2.0 / 61
    assert abs(result[0]["rrf_score"] - expected) < 1e-6


def test_rrf_output_sorted_descending(make_doc):
    """Output is sorted by RRF score, highest first."""
    doc1 = make_doc(1)
    doc2 = make_doc(2)
    result = rrf_merge([doc1, doc2], [doc1], k=60, top_k=5)
    assert result[0]["id"] == 1
    assert result[0]["rrf_score"] > result[1]["rrf_score"]


def test_rrf_rank_one_always_beats_rank_two(make_doc):
    """A doc ranked first in a source list must always outscore one ranked second."""
    doc1, doc2 = make_doc(1), make_doc(2)
    result = rrf_merge([doc1, doc2], [], k=60, top_k=5)
    scores = {r["id"]: r["rrf_score"] for r in result}
    assert scores[1] > scores[2]


@pytest.mark.parametrize("top_k,expected_len", [(0, 0), (1, 1), (3, 3), (100, 10)])
def test_rrf_top_k_limits_output(make_doc, top_k, expected_len):
    """Output length is capped by top_k, including boundary cases."""
    docs = [make_doc(i) for i in range(10)]
    result = rrf_merge(docs, [], k=60, top_k=top_k)
    assert len(result) == expected_len
